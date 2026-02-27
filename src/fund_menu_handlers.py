#!/usr/bin/env python3
"""
yspy - Fund Menu Handlers

ncurses UI handlers for managing mutual funds that have no Yahoo Finance
ticker.  All fund CRUD operations plus buy/sell unit recording.

Press 'f' from the main menu to open the fund sub-menu.

Handlers
--------
  FundMenuHandler     — top-level sub-menu (routes to the others)
  ListFundsHandler    — view all funds + current NAV + holdings
  AddFundHandler      — add a new fund (name, Avanza ID, ISIN, currency)
  RemoveFundHandler   — remove a fund and its holdings file
  BuyFundUnitsHandler — record a fund-unit purchase
  SellFundUnitsHandler — record a fund-unit sale (FIFO)

Project: https://github.com/H4jen/yspy
"""

from __future__ import annotations

import curses
import logging
from typing import List, Optional

from src.ui_handlers import BaseUIHandler


# ===========================================================================
# FundMenuHandler  (sub-menu entry point)
# ===========================================================================

class FundMenuHandler(BaseUIHandler):
    """Top-level fund sub-menu.  Think of it as a mini main-menu for funds."""

    _MENU = [
        ("1", "List Funds",             "list"),
        ("2", "Add Fund",               "add"),
        ("3", "Remove Fund",            "remove"),
        ("4", "Buy Fund Units",         "buy"),
        ("5", "Sell Fund Units",        "sell"),
    ]

    def handle(self) -> None:
        while True:
            self.stdscr.clear()
            self.safe_addstr(0, 0, "=== Managed Funds ===")

            for i, (key, label, _) in enumerate(self._MENU, start=2):
                self.safe_addstr(i, 0, f"{key}. {label}")

            fund_count = len(getattr(self.portfolio, "funds", {}))
            self.safe_addstr(len(self._MENU) + 3, 0,
                             f"Funds in portfolio: {fund_count}")
            self.safe_addstr(len(self._MENU) + 4, 0, "0. Back to main menu")
            self.safe_addstr(len(self._MENU) + 5, 0, "Select: ")
            self.stdscr.refresh()

            curses.noecho()
            self.stdscr.nodelay(False)
            key = self.stdscr.getch()

            if key == ord('0') or key == 27:  # ESC or 0
                return

            char = chr(key) if 32 <= key <= 126 else None
            action = next(
                (act for k, _, act in self._MENU if k == char), None
            )

            if action == "list":
                ListFundsHandler(self.stdscr, self.portfolio).handle()
            elif action == "add":
                AddFundHandler(self.stdscr, self.portfolio).handle()
            elif action == "remove":
                RemoveFundHandler(self.stdscr, self.portfolio).handle()
            elif action == "buy":
                BuyFundUnitsHandler(self.stdscr, self.portfolio).handle()
            elif action == "sell":
                SellFundUnitsHandler(self.stdscr, self.portfolio).handle()


# ===========================================================================
# ListFundsHandler
# ===========================================================================

class ListFundsHandler(BaseUIHandler):
    """Display all managed funds with their current NAV and unit holdings."""

    def handle(self) -> None:
        row = self.clear_and_display_header("Managed Funds – Overview")
        funds = getattr(self.portfolio, "funds", {})

        if not funds:
            self.show_message("No managed funds in portfolio.  Use 'Add Fund' to add one.", row)
            return

        # Headers
        self.safe_addstr(row,     0, f"{'NAME':<30} {'AVANZA-ID':<12} {'ISIN':<14} "
                                      f"{'CURR':<5} {'UNITS':>10} {'AVG BUY':>10} "
                                      f"{'CUR NAV':>10} {'VALUE(SEK)':>12}")
        self.safe_addstr(row + 1, 0, "-" * 105)
        row += 2

        for name, fund in funds.items():
            try:
                price_obj  = fund.get_price_info()
                nav_sek    = price_obj.get_current_sek() if price_obj else None
                total_units = fund.get_total_units()
                avg_price   = fund.get_average_price()
                value_sek   = (nav_sek * total_units) if (nav_sek and total_units) else None

                nav_str   = f"{nav_sek:.4f}"    if nav_sek   is not None else "N/A"
                value_str = f"{value_sek:.2f}"  if value_sek is not None else "N/A"
                avg_str   = f"{avg_price:.4f}"  if avg_price else "---"

                line = (
                    f"{name:<30} {fund.avanza_id:<12} {fund.isin:<14} "
                    f"{fund.currency:<5} {total_units:>10.4f} {avg_str:>10} "
                    f"{nav_str:>10} {value_str:>12}"
                )
                self.safe_addstr(row, 0, line)
            except Exception as exc:
                self.safe_addstr(row, 0, f"{name:<30} (error: {exc})")

            row += 1
            h, _ = self.stdscr.getmaxyx()
            if row >= h - 2:
                self.safe_addstr(row, 0, "  ... (more funds below, press any key)")
                self.stdscr.refresh()
                self.stdscr.getch()
                row = 2

        self.safe_addstr(row + 1, 0, "Press any key to return...")
        self.stdscr.refresh()
        self.stdscr.getch()


# ===========================================================================
# AddFundHandler
# ===========================================================================

class AddFundHandler(BaseUIHandler):
    """Add a new managed fund — enter an ISIN and the Avanza ID is resolved automatically."""

    def handle(self) -> None:
        row = self.clear_and_display_header("Add Managed Fund")

        try:
            from src.fund_provider import AvanzaFundProvider
            provider = AvanzaFundProvider()
        except Exception as exc:
            self.show_message(f"Could not load fund provider: {exc}", row)
            return

        # --- Step 1: ISIN ---
        isin_raw = self.get_user_input(
            "ISIN (e.g. SE0019175563, or press Enter to skip and enter ID manually): ", row
        )
        isin = (isin_raw or "").strip().upper()

        avanza_id   = ""
        auto_name   = ""
        auto_currency = "SEK"
        row_status  = row + 2

        if isin:
            # Check duplicate ISIN
            existing_isin = (
                self.portfolio.find_fund_name_by_isin(isin)
                if hasattr(self.portfolio, "find_fund_name_by_isin") else None
            )
            if existing_isin:
                self.show_message(f"ISIN {isin} is already used by fund '{existing_isin}'.", row_status)
                return

            self.safe_addstr(row_status, 0, f"Resolving {isin} via Avanza …")
            self.stdscr.refresh()

            try:
                resolved_id = provider.resolve_isin(isin)
                if resolved_id:
                    avanza_id = resolved_id
                    info = provider.get_fund_info(avanza_id)
                    auto_name     = info.get("name", "")
                    auto_currency = info.get("currency", "SEK") or "SEK"
                    nav           = info.get("nav")
                    nav_str = f"{nav:.2f} {auto_currency}" if nav else "N/A"
                    self.safe_addstr(row_status, 0,
                        f"Found: {auto_name}  |  ID={avanza_id}  |  NAV={nav_str}  ✓")
                else:
                    self.safe_addstr(row_status, 0,
                        "ISIN not found on Avanza. Enter Avanza ID manually below.")
            except Exception as exc:
                self.safe_addstr(row_status, 0, f"Lookup failed ({exc}). Enter ID manually.")

            self.stdscr.refresh()
            row_status += 1

        # --- Step 2: Avanza ID (pre-filled or manual) ---
        id_prompt = (
            f"Avanza orderbook ID [{avanza_id}]: " if avanza_id
            else "Avanza orderbook ID (number in the Avanza URL): "
        )
        id_raw = self.get_user_input(id_prompt, row_status)
        if id_raw and id_raw.strip():
            avanza_id = id_raw.strip()

        if not avanza_id or not avanza_id.isdigit():
            self.show_message("Cancelled – invalid Avanza ID (must be a number).", row_status + 1)
            return

        # Check duplicate Avanza ID
        existing_id = (
            self.portfolio.find_fund_name_by_avanza_id(avanza_id)
            if hasattr(self.portfolio, "find_fund_name_by_avanza_id") else None
        )
        if existing_id:
            self.show_message(
                f"Avanza ID {avanza_id} is already used by fund '{existing_id}'.",
                row_status + 1,
            )
            return

        row_status += 1

        # --- Step 3: Fund name (pre-filled from API if available) ---
        name_prompt = (
            f"Fund name [{auto_name}]: " if auto_name
            else "Fund name (human-readable): "
        )
        name_raw = self.get_user_input(name_prompt, row_status)
        name = (name_raw or "").strip() or auto_name
        if not name:
            self.show_message("Cancelled – no fund name.", row_status + 1)
            return

        funds = getattr(self.portfolio, "funds", {})
        if name in funds:
            self.show_message(f"A fund named '{name}' already exists.", row_status + 1)
            return

        row_status += 1

        # --- Step 4: Currency (pre-filled) ---
        currency_raw = self.get_user_input(f"Currency [{auto_currency}]: ", row_status)
        currency = (currency_raw or "").strip().upper() or auto_currency

        row_status += 1

        # --- Confirm ---
        if not self.confirm_action(
            f"Add '{name}'  ID={avanza_id}  ISIN={isin or 'n/a'}  {currency}?",
            row_status + 1,
        ):
            self.show_message("Cancelled.", row_status + 3)
            return

        success = self.portfolio.add_fund(
            name=name,
            avanza_id=avanza_id,
            isin=isin,
            currency=currency,
        )

        if success:
            self.show_message(f"Fund '{name}' added successfully.", row_status + 3)
        else:
            self.show_message(f"Failed to add fund '{name}'.", row_status + 3)


# ===========================================================================
# RemoveFundHandler
# ===========================================================================

class RemoveFundHandler(BaseUIHandler):
    """Remove a managed fund and delete its holdings file."""

    def handle(self) -> None:
        row = self.clear_and_display_header("Remove Managed Fund")
        funds = getattr(self.portfolio, "funds", {})

        if not funds:
            self.show_message("No managed funds in portfolio.", row)
            return

        fund_names = list(funds.keys())
        self.safe_addstr(row, 0, "Available funds:")
        for i, name in enumerate(fund_names):
            fund = funds[name]
            units = fund.get_total_units()
            self.safe_addstr(row + 1 + i, 0,
                             f"{i + 1}. {name} — {units:.4f} units (ID: {fund.avanza_id})")

        choice = self.get_numeric_input(
            "Select fund number to remove (0 to cancel): ",
            row + 1 + len(fund_names),
            min_val=0,
            max_val=len(fund_names),
            integer_only=True,
        )

        if not choice or int(choice) == 0:
            return

        selected_name = fund_names[int(choice) - 1]
        fund = funds[selected_name]
        msg_row = row + 3 + len(fund_names)

        if fund.get_total_units() > 0:
            self.safe_addstr(msg_row, 0,
                f"WARNING: '{selected_name}' still has {fund.get_total_units():.4f} units!")
            msg_row += 1

        if not self.confirm_action(
            f"Remove fund '{selected_name}' and all its data?", msg_row
        ):
            self.show_message("Cancelled.", msg_row + 2)
            return

        success = self.portfolio.remove_fund(selected_name)
        if success:
            self.show_message(f"Fund '{selected_name}' removed.", msg_row + 2)
        else:
            self.show_message(f"Failed to remove '{selected_name}'.", msg_row + 2)


# ===========================================================================
# BuyFundUnitsHandler
# ===========================================================================

class BuyFundUnitsHandler(BaseUIHandler):
    """Record a fund-unit purchase (add to holdings)."""

    def handle(self) -> None:
        row = self.clear_and_display_header("Buy Fund Units")
        funds = getattr(self.portfolio, "funds", {})

        if not funds:
            self.show_message("No managed funds.  Add a fund first.", row)
            return

        fund_names = list(funds.keys())
        self.safe_addstr(row, 0, "Available funds:")
        for i, name in enumerate(fund_names):
            fund = funds[name]
            units = fund.get_total_units()
            self.safe_addstr(row + 1 + i, 0,
                             f"{i + 1}. {name}  (current holdings: {units:.4f} units)")

        choice = self.get_numeric_input(
            "Select fund (0 to cancel): ",
            row + 1 + len(fund_names),
            min_val=0,
            max_val=len(fund_names),
            integer_only=True,
        )

        if not choice or int(choice) == 0:
            return

        selected_name = fund_names[int(choice) - 1]
        fund = funds[selected_name]
        base_row = row + 3 + len(fund_names)

        # Try to fetch current NAV as a helpful default hint
        try:
            price_obj = fund.get_price_info()
            current_nav = price_obj.get_current_sek() if price_obj else None
            nav_hint = f" (current NAV ≈ {current_nav:.4f})" if current_nav else ""
        except Exception:
            nav_hint = ""

        units = self.get_numeric_input(
            f"Number of units to buy for '{selected_name}': ",
            base_row,
            min_val=0.0001,
        )
        if units is None:
            self.show_message("Cancelled – invalid unit count.", base_row + 2)
            return

        price = self.get_numeric_input(
            f"Purchase NAV per unit{nav_hint}: ",
            base_row + 1,
            min_val=0.0001,
        )
        if price is None:
            self.show_message("Cancelled – invalid price.", base_row + 3)
            return

        total_cost = units * price
        self.safe_addstr(base_row + 3, 0,
            f"Summary: {units:.4f} units of '{selected_name}' at {price:.4f} = {total_cost:.2f} {fund.currency}")

        if not self.confirm_action("Confirm purchase?", base_row + 4):
            self.show_message("Purchase cancelled.", base_row + 6)
            return

        success = self.portfolio.add_fund_units(selected_name, units, price)
        if hasattr(self.portfolio, "highlight_stock") and success:
            # Auto-highlight so the fund appears in the watch screen's owned list
            try:
                self.portfolio.highlight_stock(selected_name)
            except Exception:
                pass

        if success:
            self.show_message(
                f"Bought {units:.4f} units of '{selected_name}'.  "
                f"Total holdings: {fund.get_total_units():.4f} units.",
                base_row + 6,
            )
        else:
            self.show_message(f"Failed to record purchase for '{selected_name}'.", base_row + 6)


# ===========================================================================
# SellFundUnitsHandler
# ===========================================================================

class SellFundUnitsHandler(BaseUIHandler):
    """Record a fund-unit sale (removes holdings via FIFO)."""

    def handle(self) -> None:
        row = self.clear_and_display_header("Sell Fund Units")
        funds = getattr(self.portfolio, "funds", {})

        # Only show funds with units
        owned = {n: f for n, f in funds.items() if f.get_total_units() > 0}

        if not owned:
            self.show_message("No funds with units to sell.", row)
            return

        fund_names = list(owned.keys())
        self.safe_addstr(row, 0, "Funds with holdings:")
        for i, name in enumerate(fund_names):
            fund = owned[name]
            self.safe_addstr(row + 1 + i, 0,
                             f"{i + 1}. {name}  ({fund.get_total_units():.4f} units  "
                             f"avg {fund.get_average_price():.4f} {fund.currency})")

        choice = self.get_numeric_input(
            "Select fund (0 to cancel): ",
            row + 1 + len(fund_names),
            min_val=0,
            max_val=len(fund_names),
            integer_only=True,
        )

        if not choice or int(choice) == 0:
            return

        selected_name = fund_names[int(choice) - 1]
        fund = owned[selected_name]
        base_row = row + 3 + len(fund_names)

        available = fund.get_total_units()
        units = self.get_numeric_input(
            f"Units to sell (available: {available:.4f}): ",
            base_row,
            min_val=0.0001,
            max_val=available,
        )
        if units is None:
            self.show_message("Cancelled – invalid unit count.", base_row + 2)
            return

        price = self.get_numeric_input(
            f"Sale NAV per unit: ",
            base_row + 1,
            min_val=0.0001,
        )
        if price is None:
            self.show_message("Cancelled – invalid price.", base_row + 3)
            return

        proceeds = units * price
        avg_cost  = fund.get_average_price()
        pnl       = (price - avg_cost) * units

        self.safe_addstr(base_row + 3, 0,
            f"Summary: sell {units:.4f} units at {price:.4f}, "
            f"proceeds = {proceeds:.2f} {fund.currency}")
        self.safe_addstr(base_row + 4, 0,
            f"Estimated P/L vs avg cost: {pnl:+.2f} {fund.currency}")

        if not self.confirm_action("Confirm sale?", base_row + 5):
            self.show_message("Sale cancelled.", base_row + 7)
            return

        success = self.portfolio.sell_fund_units(selected_name, units, price)
        if success:
            remaining = fund.get_total_units()
            self.show_message(
                f"Sold {units:.4f} units of '{selected_name}'.  "
                f"Remaining: {remaining:.4f} units.",
                base_row + 7,
            )
        else:
            self.show_message(
                f"Failed to sell units for '{selected_name}'.", base_row + 7
            )
