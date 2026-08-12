#!/usr/bin/env python3
"""Measure Yahoo Finance sequential versus bounded-batch download performance.

This is a network benchmark, not a unit test. It does not write portfolio data.
"""

import argparse
import math
import sys
import time
from datetime import date, timedelta
from typing import Iterable

import yfinance as yf


def batches(items: list[str], batch_size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


def load_tickers(limit: int) -> list[str]:
    try:
        from src.update_historical_prices import discover_portfolio_stocks
    except ImportError as exc:
        raise RuntimeError("Run this script from the repository root") from exc

    tickers = list(dict.fromkeys(discover_portfolio_stocks().values()))
    if not tickers:
        raise RuntimeError("No portfolio tickers were discovered")
    return tickers[:limit] if limit else tickers


def sequential_fetch(tickers: list[str], start_date: str, end_date: str, throttle: float) -> tuple[float, int]:
    started_at = time.perf_counter()
    successes = 0

    for ticker in tickers:
        try:
            frame = yf.Ticker(ticker).history(start=start_date, end=end_date, auto_adjust=True)
            successes += int(not frame.empty)
        except Exception as exc:
            print(f"  sequential failure for {ticker}: {exc}", file=sys.stderr)
        time.sleep(throttle)

    return time.perf_counter() - started_at, successes


def bulk_fetch(tickers: list[str], start_date: str, end_date: str, batch_size: int) -> tuple[float, int, int]:
    started_at = time.perf_counter()
    successes = 0
    request_count = 0

    for ticker_batch in batches(tickers, batch_size):
        request_count += 1
        try:
            frame = yf.download(
                ticker_batch,
                start=start_date,
                end=end_date,
                auto_adjust=True,
                group_by="ticker",
                progress=False,
            )
            if frame is None or frame.empty:
                continue
            if len(ticker_batch) == 1:
                successes += 1
                continue

            available_tickers = set(frame.columns.get_level_values(0))
            successes += sum(ticker in available_tickers for ticker in ticker_batch)
        except Exception as exc:
            joined_tickers = ", ".join(ticker_batch)
            print(f"  bulk failure for {joined_tickers}: {exc}", file=sys.stderr)

    return time.perf_counter() - started_at, successes, request_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=12, help="Maximum discovered portfolio tickers (default: 12)")
    parser.add_argument("--batch-size", type=int, default=10, help="Tickers per bulk download (default: 10)")
    parser.add_argument("--days", type=int, default=30, help="Calendar days of history to request (default: 30)")
    parser.add_argument("--throttle", type=float, default=0.3, help="Sequential delay matching the current updater (default: 0.3)")
    arguments = parser.parse_args()

    if arguments.limit < 1 or arguments.batch_size < 1 or arguments.days < 1 or arguments.throttle < 0:
        parser.error("limit, batch-size, and days must be positive; throttle must not be negative")

    tickers = load_tickers(arguments.limit)
    end_date = date.today()
    start_date = end_date - timedelta(days=arguments.days)

    print(f"Tickers: {len(tickers)} | range: {start_date} to {end_date} | batch size: {arguments.batch_size}")
    print("Sequential benchmark: current per-ticker updater pattern")
    sequential_seconds, sequential_successes = sequential_fetch(
        tickers, str(start_date), str(end_date), arguments.throttle
    )
    print(f"  {sequential_seconds:.2f}s | {len(tickers)} requests | {sequential_successes}/{len(tickers)} symbols returned data")

    print("Bulk benchmark: proposed bounded yf.download batches")
    bulk_seconds, bulk_successes, bulk_requests = bulk_fetch(
        tickers, str(start_date), str(end_date), arguments.batch_size
    )
    print(f"  {bulk_seconds:.2f}s | {bulk_requests} requests | {bulk_successes}/{len(tickers)} symbols returned data")

    request_reduction = len(tickers) - bulk_requests
    time_saved = sequential_seconds - bulk_seconds
    speedup = sequential_seconds / bulk_seconds if bulk_seconds else math.inf
    print("Result")
    print(f"  Request reduction: {request_reduction} ({len(tickers)} -> {bulk_requests})")
    print(f"  Elapsed-time change: {time_saved:+.2f}s ({speedup:.2f}x sequential/bulk)")
    print("  Network timings vary; repeat the command before setting a production batch size.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())