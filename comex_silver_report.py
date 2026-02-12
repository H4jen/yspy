#!/usr/bin/env python3
"""
COMEX Silver Data Report
========================
Fetches official silver data from CME Group / COMEX:
  1) Downloads the Metals Issues & Stops YTD delivery report (.xls)
  2) Extracts essential silver delivery data
  3) Downloads silver futures contract data (settlements, volume, open interest)
  4) Evaluates contracts, calculates silver delivered and on order (3 months ahead)
  5) Produces a text summary of findings

Silver futures contract spec:
  - Symbol: SI
  - Contract size: 5,000 troy ounces
  - Exchange: COMEX (CME Group)
"""

import os
import sys
import json
import time
import io
from datetime import datetime, timedelta
from collections import OrderedDict

import requests
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "comex_data")
SILVER_CONTRACT_SIZE_OZ = 5000  # 5,000 troy oz per full-size silver futures contract
TROY_OZ_PER_KG = 32.1507

# CME Group URLs
DELIVERY_REPORT_URL = "https://www.cmegroup.com/delivery_reports/MetalsIssuesAndStopsYTDReport.xls"
WAREHOUSE_STOCKS_URL = "https://www.cmegroup.com/delivery_reports/Silver_stocks.xls"

# CME Group API endpoints for silver futures (product ID 458 = Silver Futures)
SETTLEMENTS_URL = "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/458/FUT"
VOLUME_URL = "https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/SI/FUT"

# Alternative: scrape the HTML pages
SETTLEMENTS_PAGE = "https://www.cmegroup.com/markets/metals/precious/silver.settlements.html"
VOLUME_PAGE = "https://www.cmegroup.com/markets/metals/precious/silver.volume.html"

# Request headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cmegroup.com/markets/metals/precious/silver.html",
}

# JSON API headers
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cmegroup.com/markets/metals/precious/silver.settlements.html",
    "X-Requested-With": "XMLHttpRequest",
}

# ---------------------------------------------------------------------------
# Contract month helpers
# ---------------------------------------------------------------------------
MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
MONTH_NAMES = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}
MONTH_NAME_TO_NUM = {v: k for k, v in MONTH_NAMES.items()}


def contract_month_label(month_num, year):
    """Return e.g. 'MAR 2026'."""
    return f"{MONTH_NAMES[month_num]} {year}"


def months_in_range(start_date, num_months=3):
    """Return list of (month_num, year) for num_months starting from start_date."""
    result = []
    m, y = start_date.month, start_date.year
    for _ in range(num_months + 1):  # include current month + 3 ahead
        result.append((m, y))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


# ---------------------------------------------------------------------------
# 1) Download delivery report XLS
# ---------------------------------------------------------------------------
def download_delivery_report(force=False):
    """Download the Metals Issues & Stops YTD delivery report (.xls)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    filepath = os.path.join(CACHE_DIR, "MetalsIssuesAndStopsYTDReport.xls")

    if not force and os.path.exists(filepath):
        age_hours = (time.time() - os.path.getmtime(filepath)) / 3600
        if age_hours < 12:
            print(f"  Using cached delivery report ({age_hours:.1f}h old)")
            return filepath

    # Try multiple delivery report URLs
    delivery_urls = [
        "https://www.cmegroup.com/delivery_reports/MetalsIssuesAndStopsYTDReport.xls",
        "https://www.cmegroup.com/delivery_reports/MetalsIssuesAndStopsReport.xls",
    ]

    # Use a session with cookies to appear as a real browser
    session = requests.Session()
    session.headers.update(HEADERS)

    # First visit the main page to get cookies
    try:
        session.get("https://www.cmegroup.com/markets/metals/precious/silver.html", timeout=15)
    except Exception:
        pass

    for url in delivery_urls:
        print(f"  Trying: {url.split('/')[-1]}...")
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                print(f"  Downloaded ({len(resp.content):,} bytes)")
                return filepath
            else:
                print(f"  HTTP {resp.status_code} ({len(resp.content)} bytes)")
        except Exception as e:
            print(f"  Failed: {e}")

    print(f"  WARNING: Could not download delivery report (CME may block automated access)")
    print(f"  Delivery data will be estimated from contract open interest instead.")
    return None


# ---------------------------------------------------------------------------
# 1b) Download COMEX Silver Warehouse Stocks XLS
# ---------------------------------------------------------------------------
def download_warehouse_stocks(force=False):
    """Download the Silver warehouse stocks report (.xls) from CME."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    filepath = os.path.join(CACHE_DIR, "Silver_stocks.xls")

    if not force and os.path.exists(filepath):
        age_hours = (time.time() - os.path.getmtime(filepath)) / 3600
        if age_hours < 12:
            print(f"  Using cached warehouse stocks ({age_hours:.1f}h old)")
            return filepath

    print(f"  Downloading Silver warehouse stocks from CME Group...")
    try:
        resp = requests.get(WAREHOUSE_STOCKS_URL, headers=HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(filepath, "wb") as f:
                f.write(resp.content)
            print(f"  Downloaded ({len(resp.content):,} bytes)")
            return filepath
        else:
            print(f"  HTTP {resp.status_code} ({len(resp.content)} bytes)")
    except Exception as e:
        print(f"  Failed: {e}")

    print(f"  WARNING: Could not download warehouse stocks report.")
    return None


# ---------------------------------------------------------------------------
# 1c) Parse Silver Warehouse Stocks (Registered & Eligible)
# ---------------------------------------------------------------------------
def parse_warehouse_stocks(xls_path):
    """
    Parse the Silver_stocks.xls and extract registered/eligible data
    per vault and totals.
    """
    if xls_path is None:
        return None

    print(f"  Parsing warehouse stocks report...")
    try:
        df = pd.read_excel(xls_path, header=None)

        # Extract report date and activity date
        report_date = None
        activity_date = None
        for idx, row in df.iterrows():
            for val in row.values:
                s = str(val).strip()
                if s.startswith("Report Date:"):
                    report_date = s.replace("Report Date:", "").strip()
                elif s.startswith("Activity Date:"):
                    activity_date = s.replace("Activity Date:", "").strip()

        # Parse vault-by-vault data
        vaults = []
        current_vault = None
        total_registered = 0
        total_eligible = 0
        total_combined = 0

        for idx, row in df.iterrows():
            col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
            col7 = row.iloc[7] if len(row) > 7 and pd.notna(row.iloc[7]) else None  # TOTAL TODAY

            # Grand totals
            if col0 == "TOTAL REGISTERED":
                total_registered = float(col7) if col7 else 0
                continue
            elif col0 == "TOTAL ELIGIBLE":
                total_eligible = float(col7) if col7 else 0
                continue
            elif col0 == "COMBINED TOTAL":
                total_combined = float(col7) if col7 else 0
                continue

            # Vault header (all-caps, not a category label)
            if (col0 and col0 not in ("", "nan", "NaN", "DEPOSITORY", "Troy Ounce",
                "SILVER", "COMMODITY EXCHANGE, INC.", "METAL DEPOSITORY STATISTICS")
                and col0 not in ("Registered", "Eligible", "Total")
                and not col0.startswith("TOTAL") and not col0.startswith("COMBINED")
                and not col0.startswith("The information") and not col0.startswith("the Commodity")
                and not col0.startswith("This report") and not col0.startswith("For questions")
                and col7 is None):
                current_vault = col0
                continue

            # Registered / Eligible / Total rows under a vault
            if col0 in ("Registered", "Eligible", "Total") and current_vault and col7 is not None:
                today = float(col7) if col7 else 0
                prev = float(row.iloc[2]) if pd.notna(row.iloc[2]) else 0
                received = float(row.iloc[3]) if pd.notna(row.iloc[3]) else 0
                withdrawn = float(row.iloc[4]) if pd.notna(row.iloc[4]) else 0
                net_change = float(row.iloc[5]) if pd.notna(row.iloc[5]) else 0
                adjustment = float(row.iloc[6]) if pd.notna(row.iloc[6]) else 0

                if col0 == "Registered":
                    vault_entry = {
                        "vault": current_vault,
                        "registered_prev": prev,
                        "registered_today": today,
                    }
                elif col0 == "Eligible":
                    if vaults and vaults[-1]["vault"] == current_vault:
                        vaults[-1]["eligible_prev"] = prev
                        vaults[-1]["eligible_today"] = today
                    else:
                        vault_entry = {
                            "vault": current_vault,
                            "eligible_prev": prev,
                            "eligible_today": today,
                        }
                elif col0 == "Total":
                    if vaults and vaults[-1]["vault"] == current_vault:
                        vaults[-1]["total_prev"] = prev
                        vaults[-1]["total_today"] = today
                        vaults[-1]["received"] = received
                        vaults[-1]["withdrawn"] = withdrawn
                        vaults[-1]["net_change"] = net_change
                    continue

                if col0 in ("Registered",) and current_vault:
                    vaults.append(vault_entry)

        result = {
            "report_date": report_date,
            "activity_date": activity_date,
            "total_registered_oz": total_registered,
            "total_eligible_oz": total_eligible,
            "total_combined_oz": total_combined,
            "vaults": vaults,
        }

        # Convert to tonnes for convenience
        result["total_registered_tonnes"] = total_registered / TROY_OZ_PER_KG / 1000
        result["total_eligible_tonnes"] = total_eligible / TROY_OZ_PER_KG / 1000
        result["total_combined_tonnes"] = total_combined / TROY_OZ_PER_KG / 1000

        print(f"  Report Date: {report_date}")
        print(f"  Activity Date: {activity_date}")
        print(f"  Found {len(vaults)} depositories")
        print(f"  Total Registered: {total_registered:,.0f} oz ({result['total_registered_tonnes']:,.1f} t)")
        print(f"  Total Eligible:   {total_eligible:,.0f} oz ({result['total_eligible_tonnes']:,.1f} t)")
        print(f"  Combined Total:   {total_combined:,.0f} oz ({result['total_combined_tonnes']:,.1f} t)")

        return result

    except Exception as e:
        print(f"  Error parsing warehouse stocks: {e}")
        import traceback
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# 2) Extract silver delivery data from XLS
# ---------------------------------------------------------------------------
def extract_silver_deliveries(xls_path):
    """Parse the delivery report and extract silver-specific data."""
    if xls_path is None:
        print("  No delivery report available, using CME web data instead.")
        return None

    print(f"  Parsing delivery report...")
    try:
        # The XLS may have multiple sheets; try common sheet names
        xls = pd.ExcelFile(xls_path)
        silver_data = []

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)

            # Search for silver-related rows
            for idx, row in df.iterrows():
                row_str = " ".join(str(v) for v in row.values if pd.notna(v)).upper()
                if "SILVER" in row_str or "SI " in row_str:
                    silver_data.append({
                        "sheet": sheet_name,
                        "row": idx,
                        "data": [v for v in row.values if pd.notna(v)],
                    })

        if silver_data:
            print(f"  Found {len(silver_data)} silver-related entries in delivery report")
        else:
            print("  No silver entries found in delivery report sheets")

        return silver_data

    except Exception as e:
        print(f"  Error parsing XLS: {e}")
        return None


# ---------------------------------------------------------------------------
# 3) Download contract data (settlements + volume/OI) from CME
# ---------------------------------------------------------------------------
def get_last_trade_date():
    """Get the most recent trade date in MM/DD/YYYY format for CME API calls."""
    now = datetime.now()
    # If before 6 PM CT (roughly 00:00 UTC next day), use yesterday
    # CME settlements are published after market close ~5:00 PM CT
    candidate = now - timedelta(days=1)
    # Skip weekends
    while candidate.weekday() >= 5:  # 5=Saturday, 6=Sunday
        candidate -= timedelta(days=1)
    return candidate.strftime("%m/%d/%Y")


def fetch_settlements_data():
    """Fetch silver futures settlement data from CME Group JSON API."""
    print(f"  Fetching settlement data...")

    trade_date = get_last_trade_date()
    print(f"  Trade date: {trade_date}")

    # Try dates going back up to 5 business days
    for day_offset in range(6):
        dt = datetime.now() - timedelta(days=1 + day_offset)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        td = dt.strftime("%m/%d/%Y")

        url = (f"https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/"
               f"Settlements/458/FUT?strategy=DEFAULT&tradeDate={td}&pageSize=50")
        try:
            resp = requests.get(url, headers=API_HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                settlements = data.get("settlements", [])
                # Filter out the "Total" row and empty entries
                real = [s for s in settlements
                        if s.get("month", "").upper() != "TOTAL"
                        and parse_number(s.get("openInterest", 0)) > 0]
                if real:
                    print(f"  Retrieved {len(real)} active contract months "
                          f"(trade date: {data.get('tradeDate', td)})")
                    print(f"  Report type: {data.get('reportType', 'N/A')}")
                    return data
        except Exception as e:
            print(f"  API attempt for {td} failed: {e}")
            continue

    print("  WARNING: Could not fetch settlement data from CME API.")
    return None


def fetch_volume_oi_data():
    """Fetch silver futures volume and open interest data from CME API."""
    print(f"  Fetching volume & open interest data...")

    # The volume API uses a different date format and URL pattern
    for day_offset in range(6):
        dt = datetime.now() - timedelta(days=1 + day_offset)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        td = dt.strftime("%m/%d/%Y")

        # Try multiple API URL patterns
        urls = [
            f"https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/SI/FUT?tradeDate={td}",
            f"https://www.cmegroup.com/CmeWS/mvc/Volume/Details/458/FUT?tradeDate={td}",
        ]

        for url in urls:
            try:
                resp = requests.get(url, headers=API_HEADERS, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data:
                        print(f"  Retrieved volume/OI data for {td}")
                        return data
                    elif isinstance(data, list) and data:
                        print(f"  Retrieved volume/OI data for {td}")
                        return {"records": data}
            except (json.JSONDecodeError, Exception):
                continue

    print("  Volume API not available (data will come from settlements).")
    return None


# ---------------------------------------------------------------------------
# 4) Evaluate contract data, calculate deliveries and standing-for-delivery
# ---------------------------------------------------------------------------
def parse_number(s):
    """Parse a number string that may have commas, +/- signs, or letters."""
    if s is None:
        return 0
    s = str(s).strip().replace(",", "").replace("+", "")
    # Remove trailing letters like 'A', 'B' (ask/bid indicators)
    while s and s[-1].isalpha():
        s = s[:-1]
    try:
        return float(s) if "." in s else int(s)
    except (ValueError, TypeError):
        return 0


def evaluate_contracts(settlements_data, volume_data, delivery_data):
    """
    Evaluate silver futures contracts for the next 3 months.
    Calculate delivered ounces and ounces standing for delivery.
    """
    now = datetime.now()
    target_months = months_in_range(now, num_months=3)
    print(f"\n  Analyzing contracts for: {', '.join(contract_month_label(m, y) for m, y in target_months)}")

    contracts = OrderedDict()

    # --- Parse settlement data from JSON API ---
    if settlements_data and "settlements" in settlements_data:
        trade_date = settlements_data.get("tradeDate", "")
        for entry in settlements_data["settlements"]:
            month_str = entry.get("month", "").upper()
            if month_str == "TOTAL":
                continue  # skip summary row

            settle = parse_number(entry.get("settle", 0))
            volume = parse_number(entry.get("volume", 0))
            oi = parse_number(entry.get("openInterest", 0))
            change = parse_number(entry.get("change", 0))
            high = parse_number(entry.get("high", 0))
            low = parse_number(entry.get("low", 0))
            last = parse_number(entry.get("last", 0))

            contracts[month_str] = {
                "month_label": month_str,
                "settle_price": settle,
                "high": high,
                "low": low,
                "last": last,
                "volume": volume,
                "open_interest": oi,
                "change": change,
                "trade_date": trade_date,
                "source": "cme_api",
            }

    # --- Calculate silver ounces ---
    results = []
    for label, c in contracts.items():
        oi = c.get("open_interest", 0) or c.get("oi_at_close", 0)
        deliveries = c.get("deliveries_today", 0)
        settle = c.get("settle_price", 0)

        oz_standing = oi * SILVER_CONTRACT_SIZE_OZ
        oz_delivered_today = deliveries * SILVER_CONTRACT_SIZE_OZ
        kg_standing = oz_standing / TROY_OZ_PER_KG
        tonnes_standing = kg_standing / 1000

        c["oz_standing_for_delivery"] = oz_standing
        c["oz_delivered_today"] = oz_delivered_today
        c["kg_standing"] = kg_standing
        c["tonnes_standing"] = tonnes_standing

        results.append(c)

    # --- Parse delivery report data ---
    delivery_summary = {}
    if delivery_data:
        for entry in delivery_data:
            data = entry.get("data", [])
            if len(data) >= 3:
                delivery_summary[str(data[0])] = data

    return results, delivery_summary


# ---------------------------------------------------------------------------
# 5) Generate text summary
# ---------------------------------------------------------------------------
def generate_summary(contracts, delivery_summary, silver_price=None, warehouse_data=None):
    """Generate a comprehensive text summary of COMEX silver data."""
    now = datetime.now()
    target_months = months_in_range(now, num_months=3)
    target_labels = set()
    for m, y in target_months:
        target_labels.add(f"{MONTH_NAMES[m]} {y}")
        target_labels.add(f"{MONTH_NAMES[m]} {str(y)[2:]}")

    lines = []
    lines.append("=" * 78)
    lines.append("  COMEX SILVER FUTURES — DATA REPORT")
    lines.append(f"  Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 78)
    lines.append("")

    # --- Current price ---
    if silver_price:
        lines.append(f"  Current Silver Price: ${silver_price:.3f} / troy oz")
        lines.append("")

    # --- Contract overview ---
    lines.append("-" * 78)
    lines.append("  SILVER FUTURES CONTRACTS — NEXT 3 MONTHS")
    lines.append("-" * 78)
    lines.append("")
    lines.append(f"  {'Contract':<12} {'Settle $':>10} {'Open Int':>12} {'Volume':>10} "
                 f"{'Chg $':>8} {'Standing (oz)':>16} {'Standing (t)':>14}")
    lines.append(f"  {'─' * 10:<12} {'─' * 8:>10} {'─' * 10:>12} {'─' * 8:>10} "
                 f"{'─' * 6:>8} {'─' * 14:>16} {'─' * 12:>14}")

    total_oi = 0
    total_oz_standing = 0
    total_tonnes = 0
    active_contracts = []

    for c in contracts:
        label = c.get("month_label", "???")
        # Check if this is one of our target months
        is_target = any(label.upper().startswith(tl.split()[0]) and
                       label.upper().endswith(tl.split()[-1]) if len(tl.split()) > 1
                       else label.upper().startswith(tl)
                       for tl in target_labels)

        oi = c.get("open_interest", 0)
        settle = c.get("settle_price", 0)
        vol = c.get("volume", 0)
        px_chg = c.get("change", 0)
        oz = c.get("oz_standing_for_delivery", 0)
        tonnes = c.get("tonnes_standing", 0)

        if oi > 0 or is_target:
            marker = " *" if is_target else "  "
            lines.append(f"{marker}{label:<12} {settle:>10,.3f} {oi:>12,} {vol:>10,} "
                        f"{px_chg:>+8.3f} {oz:>16,} {tonnes:>14,.1f}")
            active_contracts.append(c)

            if is_target:
                total_oi += oi
                total_oz_standing += oz
                total_tonnes += tonnes

    lines.append("")
    lines.append(f"  * = Target months (current + 3 months ahead)")
    lines.append("")

    # --- Delivery summary ---
    lines.append("-" * 78)
    lines.append("  DELIVERY & STANDING SUMMARY (Target Period)")
    lines.append("-" * 78)
    lines.append("")
    lines.append(f"  Total Open Interest (target months):   {total_oi:>12,} contracts")
    lines.append(f"  Silver Standing for Delivery:          {total_oz_standing:>12,} troy oz")
    lines.append(f"                                         {total_tonnes:>12,.1f} metric tonnes")
    lines.append(f"                                         {total_tonnes * 1000:>12,.0f} kg")
    lines.append("")

    if silver_price and silver_price > 0:
        total_value = total_oz_standing * silver_price
        lines.append(f"  Notional Value of Standing Silver:     ${total_value:>14,.0f}")
        lines.append("")

    # --- Delivery report data ---
    if delivery_summary:
        lines.append("-" * 78)
        lines.append("  YTD DELIVERY REPORT (from CME Issues & Stops)")
        lines.append("-" * 78)
        lines.append("")
        for key, data in delivery_summary.items():
            lines.append(f"  {' | '.join(str(d) for d in data)}")
        lines.append("")

    # --- All contracts overview ---
    lines.append("-" * 78)
    lines.append("  ALL ACTIVE CONTRACTS OVERVIEW")
    lines.append("-" * 78)
    lines.append("")

    all_oi = sum(c.get("open_interest", 0) for c in contracts)
    all_oz = sum(c.get("oz_standing_for_delivery", 0) for c in contracts)
    all_tonnes = all_oz / TROY_OZ_PER_KG / 1000

    lines.append(f"  Total Open Interest (all months):      {all_oi:>12,} contracts")
    lines.append(f"  Total Silver Represented:              {all_oz:>12,} troy oz")
    lines.append(f"                                         {all_tonnes:>12,.1f} metric tonnes")
    lines.append("")

    if silver_price and silver_price > 0:
        all_value = all_oz * silver_price
        lines.append(f"  Total Notional Value:                  ${all_value:>14,.0f}")
        lines.append("")

    # --- Key observations ---
    lines.append("-" * 78)
    lines.append("  KEY OBSERVATIONS")
    lines.append("-" * 78)
    lines.append("")

    # --- COMEX Warehouse Stocks: Registered & Eligible ---
    if warehouse_data:
        lines.append("-" * 78)
        lines.append("  COMEX WAREHOUSE SILVER STOCKS (Registered & Eligible)")
        if warehouse_data.get("report_date"):
            lines.append(f"  Report Date: {warehouse_data['report_date']}  |  "
                        f"Activity Date: {warehouse_data.get('activity_date', 'N/A')}")
        lines.append("-" * 78)
        lines.append("")

        reg_oz = warehouse_data.get("total_registered_oz", 0)
        elig_oz = warehouse_data.get("total_eligible_oz", 0)
        comb_oz = warehouse_data.get("total_combined_oz", 0)
        reg_t = warehouse_data.get("total_registered_tonnes", 0)
        elig_t = warehouse_data.get("total_eligible_tonnes", 0)
        comb_t = warehouse_data.get("total_combined_tonnes", 0)

        lines.append(f"  {'Category':<22} {'Troy Ounces':>18} {'Metric Tonnes':>16}")
        lines.append(f"  {'─' * 20:<22} {'─' * 16:>18} {'─' * 14:>16}")
        lines.append(f"  {'Registered':<22} {reg_oz:>18,.0f} {reg_t:>16,.1f}")
        lines.append(f"  {'Eligible':<22} {elig_oz:>18,.0f} {elig_t:>16,.1f}")
        lines.append(f"  {'Combined Total':<22} {comb_oz:>18,.0f} {comb_t:>16,.1f}")
        lines.append("")

        if silver_price and silver_price > 0:
            reg_value = reg_oz * silver_price
            elig_value = elig_oz * silver_price
            comb_value = comb_oz * silver_price
            lines.append(f"  Registered Value:    ${reg_value:>18,.0f}")
            lines.append(f"  Eligible Value:      ${elig_value:>18,.0f}")
            lines.append(f"  Combined Value:      ${comb_value:>18,.0f}")
            lines.append("")

        # Coverage ratio: OI vs warehouse stocks
        if comb_oz > 0 and total_oz_standing > 0:
            coverage = comb_oz / total_oz_standing * 100
            lines.append(f"  Warehouse Coverage Ratio:  {coverage:>8.1f}%")
            lines.append(f"    (warehouse silver / silver standing for delivery in target period)")
            if coverage < 100:
                lines.append(f"    ⚠  Warehouse stocks BELOW contracts standing for delivery!")
            lines.append("")

        # Per-vault breakdown
        vaults = warehouse_data.get("vaults", [])
        if vaults:
            lines.append(f"  {'Depository':<42} {'Registered':>14} {'Eligible':>14}")
            lines.append(f"  {'─' * 40:<42} {'─' * 12:>14} {'─' * 12:>14}")
            for v in vaults:
                name = v.get('vault', '?')[:40]
                reg = v.get('registered_today', 0)
                elig = v.get('eligible_today', 0)
                if reg > 0 or elig > 0:
                    lines.append(f"  {name:<42} {reg:>14,.0f} {elig:>14,.0f}")
            lines.append("")

    lines.append("-" * 78)
    lines.append("  ANALYSIS")
    lines.append("-" * 78)
    lines.append("")

    # Find the front month (highest OI among target months)
    if active_contracts:
        front = max(active_contracts,
                    key=lambda x: x.get("open_interest", 0))
        front_oi = front.get("open_interest", 0)
        front_oz = front.get("oz_standing_for_delivery", 0)
        lines.append(f"  • Front month: {front.get('month_label', '?')} with "
                    f"{front_oi:,} contracts ({front_oz:,} oz)")

    # Delivery month check — match current month AND current year
    current_label = f"{MONTH_NAMES[now.month]} {str(now.year)[2:]}"
    for c in contracts:
        label = c.get("month_label", "").upper()
        if label == current_label:
            oi = c.get("open_interest", 0)
            if oi > 0:
                lines.append(f"  • Current delivery month ({label}): "
                            f"{oi:,} contracts still open = {oi * SILVER_CONTRACT_SIZE_OZ:,} oz")

    # Highlight contracts with large OI (potential delivery pressure)
    for c in contracts:
        oi = c.get("open_interest", 0)
        label = c.get("month_label", "")
        if oi > 5000 and label != current_label:
            lines.append(f"  • {label}: {oi:,} contracts open interest "
                        f"({oi * SILVER_CONTRACT_SIZE_OZ:,} oz standing)")

    lines.append("")
    lines.append("=" * 78)
    lines.append("  Note: 1 COMEX silver contract = 5,000 troy oz")
    lines.append("  Data source: CME Group (www.cmegroup.com)")
    lines.append("=" * 78)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Get current silver spot price
# ---------------------------------------------------------------------------
def get_silver_price():
    """Fetch current silver spot price using yfinance."""
    try:
        import yfinance as yf
        si = yf.Ticker("SI=F")
        hist = si.history(period="5d")
        if not hist.empty:
            price = hist["Close"].iloc[-1]
            print(f"  Current silver futures price: ${price:.3f}/oz")
            return price
    except Exception as e:
        print(f"  Could not fetch silver price via yfinance: {e}")

    # Try from our own portfolio data
    try:
        si_file = os.path.join(SCRIPT_DIR, "portfolio", "SI=F.json")
        if os.path.exists(si_file):
            with open(si_file) as f:
                data = json.load(f)
            if "last_price" in data:
                return data["last_price"]
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║          COMEX Silver Data Report Generator                     ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()

    # Step 0: Get current silver price
    print("[0/6] Fetching current silver price...")
    silver_price = get_silver_price()
    print()

    # Step 1: Download delivery report
    print("[1/6] Downloading COMEX delivery report...")
    xls_path = download_delivery_report()
    print()

    # Step 1b: Download warehouse stocks
    print("[1b/6] Downloading COMEX silver warehouse stocks...")
    stocks_path = download_warehouse_stocks()
    warehouse_data = parse_warehouse_stocks(stocks_path)
    print()

    # Step 2: Extract silver delivery data from XLS
    print("[2/6] Extracting silver delivery data from XLS...")
    delivery_data = extract_silver_deliveries(xls_path)
    print()

    # Step 3: Download contract data
    print("[3/6] Downloading silver futures contract data...")
    settlements = fetch_settlements_data()
    time.sleep(0.5)  # Be polite to CME servers
    volume_oi = fetch_volume_oi_data()
    print()

    # Step 4: Evaluate contract data
    print("[4/6] Evaluating contracts and calculating deliveries...")
    contracts, delivery_summary = evaluate_contracts(settlements, volume_oi, delivery_data)
    print()

    # Step 5: Generate summary
    print("[5/6] Generating summary report...")
    summary = generate_summary(contracts, delivery_summary, silver_price, warehouse_data)
    print()
    print(summary)

    # Save report to file
    report_path = os.path.join(CACHE_DIR, f"silver_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(summary)
    print(f"\n  Report saved to: {report_path}")

    # Also save as JSON for programmatic use
    json_path = os.path.join(CACHE_DIR, "silver_contracts_latest.json")
    json_data = {
        "generated": datetime.now().isoformat(),
        "silver_price_usd": silver_price,
        "contracts": contracts,
        "delivery_summary": delivery_summary,
        "warehouse_stocks": warehouse_data,
    }
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2, default=str)
    print(f"  JSON data saved to: {json_path}")


if __name__ == "__main__":
    main()
