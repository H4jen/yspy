#!/usr/bin/env python3
"""
Short Selling Data Tracker for Nordic Markets

Fetches and tracks short selling positions for stocks in the portfolio.
Integrates with Finansinspektionen and other Nordic regulatory sources.
"""

__version__ = "1.2.0"  # 2026-02-02: Added aggregated cache, extended timeouts, retry logic

import requests
import pandas as pd
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import xml.etree.ElementTree as ET
import io

logger = logging.getLogger(__name__)

@dataclass
class PositionHolder:
    """Represents an individual short position holder."""
    holder_name: str
    position_percentage: float
    position_date: str
    
@dataclass
class ShortPosition:
    """Represents a short selling position with aggregated and individual holder data."""
    ticker: str
    company_name: str
    position_holder: str  # Summary like "15 holders" or "Multiple (aggregated)"
    position_percentage: float  # Total aggregated percentage
    position_date: str
    threshold_crossed: str
    market: str  # 'SE' for Sweden, 'FI' for Finland, etc.
    individual_holders: List[PositionHolder] = None  # Individual holders with their positions
    
    def __post_init__(self):
        """Initialize individual_holders list if None."""
        if self.individual_holders is None:
            self.individual_holders = []

class ShortSellingTracker:
    """Tracks short selling positions for Nordic markets."""
    
    def __init__(self, portfolio_path: str = "portfolio"):
        self.portfolio_path = Path(portfolio_path)
        self.short_positions_file = self.portfolio_path / "short_positions.json"
        self.cache_file = self.portfolio_path / "short_selling_cache.json"
        self.aggregated_cache_file = self.portfolio_path / "aggregated_positions_cache.json"
    
    def _cache_aggregated_positions(self, positions: List['ShortPosition']) -> None:
        """Cache aggregated positions for fallback when FI.se is down."""
        try:
            cache_data = {
                'cached_at': datetime.now().isoformat(),
                'position_count': len(positions),
                'positions': [
                    {
                        'ticker': p.ticker,
                        'company_name': p.company_name,
                        'position_holder': p.position_holder,
                        'position_percentage': p.position_percentage,
                        'position_date': p.position_date,
                        'threshold_crossed': p.threshold_crossed,
                        'market': p.market
                    }
                    for p in positions
                ]
            }
            with open(self.aggregated_cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"Cached {len(positions)} aggregated positions for fallback")
        except Exception as e:
            logger.warning(f"Failed to cache aggregated positions: {e}")
    
    def _load_cached_aggregated_positions(self) -> List['ShortPosition']:
        """Load cached aggregated positions as fallback."""
        try:
            if not self.aggregated_cache_file.exists():
                return []
            
            with open(self.aggregated_cache_file) as f:
                cache_data = json.load(f)
            
            # Check cache age (max 7 days)
            cached_at = datetime.fromisoformat(cache_data.get('cached_at', '2000-01-01'))
            age_days = (datetime.now() - cached_at).days
            if age_days > 7:
                logger.warning(f"Aggregated cache is {age_days} days old - too stale to use")
                return []
            
            positions = []
            for p in cache_data.get('positions', []):
                positions.append(ShortPosition(
                    ticker=p['ticker'],
                    company_name=p['company_name'],
                    position_holder=p['position_holder'],
                    position_percentage=p['position_percentage'],
                    position_date=p['position_date'],
                    threshold_crossed=p['threshold_crossed'],
                    market=p['market']
                ))
            
            logger.info(f"Loaded {len(positions)} positions from cache (age: {age_days} days)")
            return positions
        except Exception as e:
            logger.warning(f"Failed to load cached aggregated positions: {e}")
            return []
        
    def get_portfolio_tickers(self) -> Dict[str, str]:
        """Get Nordic tickers from portfolio that need short selling tracking."""
        # Try portfolio/stockPortfolio.json first
        portfolio_file = self.portfolio_path / "stockPortfolio.json"
        
        # If not found, try parent directory
        if not portfolio_file.exists():
            portfolio_file = self.portfolio_path.parent / "stockPortfolio.json"
        
        if not portfolio_file.exists():
            logger.warning(f"Portfolio file not found at {portfolio_file}")
            return {}
            
        with open(portfolio_file) as f:
            portfolio = json.load(f)
            
        # Filter for Nordic market tickers
        nordic_tickers = {}
        for name, ticker in portfolio.items():
            if any(ticker.endswith(suffix) for suffix in ['.ST', '.HE', '.OL', '.CO']):
                nordic_tickers[name] = ticker
                
        return nordic_tickers
    
    def get_isin_for_ticker(self, ticker: str) -> Optional[str]:
        """Get ISIN code for a ticker using static mapping or yfinance."""
        try:
            # First try static mapping
            from short_selling.nordic_isin_mapping import get_isin
            isin = get_isin(ticker)
            if isin:
                logger.debug(f"Found ISIN {isin} for {ticker} (static mapping)")
                return isin
            
            # Fallback to yfinance
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            isin = info.get('isin', None)
            if isin:
                logger.debug(f"Found ISIN {isin} for {ticker} (yfinance)")
            return isin
        except Exception as e:
            logger.debug(f"Could not get ISIN for {ticker}: {e}")
            return None
    
    def build_isin_mapping(self, tickers: List[str]) -> Dict[str, str]:
        """Build mapping of tickers to ISIN codes."""
        mapping = {}
        logger.info("Building ISIN mapping for portfolio stocks...")
        for ticker in tickers:
            isin = self.get_isin_for_ticker(ticker)
            if isin:
                mapping[ticker] = isin
                logger.debug(f"{ticker} -> {isin}")
        logger.info(f"Built ISIN mapping for {len(mapping)}/{len(tickers)} stocks")
        return mapping
    
    def fetch_fi_ods_file(self, file_type: str = 'current', timeout: int = None) -> Optional[pd.DataFrame]:
        """
        Fetch .ods files from Finansinspektionen's AJAX endpoints.
        
        Args:
            file_type: 'current', 'historical', or 'aggregated'
            timeout: Request timeout in seconds (default: 20 for current, 45 for aggregated)
            
        Returns:
            DataFrame with columns depending on file type:
            - aggregated: Company Name, LEI, Short %, Date (4 columns)
            - current/historical: Position Holder, Company Name, ISIN, Short %, Date, Comment (6 columns)
        """
        try:
            # Map file types to FI's endpoints
            endpoints = {
                'current': '/BlankningsRegister/GetAktuellFile',
                'historical': '/BlankningsRegister/GetHistFile', 
                'aggregated': '/BlankningsRegister/GetBlankningsregisterAggregat'
            }
            
            if file_type not in endpoints:
                logger.error(f"Invalid file type: {file_type}")
                return None
            
            # Default timeouts: aggregated file is larger and needs more time
            if timeout is None:
                timeout = 45 if file_type == 'aggregated' else 20
                
            url = f"https://www.fi.se{endpoints[file_type]}"
            
            logger.info(f"Fetching {file_type} short positions file from FI (timeout={timeout}s)...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Accept': 'application/vnd.oasis.opendocument.spreadsheet'
            }
            
            response = requests.get(url, headers=headers, timeout=timeout)
            
            if response.status_code == 200:
                # Parse the .ods file with pandas
                try:
                    # FI .ods files structure:
                    # - Aggregated file: simpler structure, data starts at row 6 (4 columns)
                    # - Current/Historical files: detailed structure, data starts at row 6 (6 columns)
                    
                    df = pd.read_excel(
                        io.BytesIO(response.content),
                        engine='odf',
                        skiprows=6,
                        header=None
                    )
                    
                    logger.info(f"✓ Downloaded {file_type} file with {len(df)} rows and {len(df.columns)} columns")
                    return df
                except ImportError as e:
                    logger.error(f"Required library not available - please install odfpy")
                    logger.info("Install with: pip install odfpy")
                    logger.debug(f"Import error details: {e}")
                    return None
                except Exception as e:
                    logger.error(f"Error parsing .ods file: {e}")
                    return None
            else:
                logger.warning(f"Failed to download {file_type} file: HTTP {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error fetching {file_type} file: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {file_type} file: {e}")
            return None

    def parse_fi_dataframe(self, df: pd.DataFrame, file_type: str) -> List[ShortPosition]:
        """
        Parse DataFrame from FI .ods files into ShortPosition objects.
        
        Two file formats:
        - 'current' and 'historical': Show individual position holders (6 columns)
        - 'aggregated': Show totals per company (4 columns, already aggregated)
        
        Args:
            df: DataFrame from .ods file
            file_type: Type of file ('current', 'historical', or 'aggregated')
            
        Returns:
            List of ShortPosition objects (one per company)
        """
        positions = []
        
        if df is None or df.empty:
            return positions
            
        try:
            # Check if this is the aggregated format (4 columns) or detailed format (6 columns)
            if len(df.columns) == 4:
                # Aggregated format: Company Name, LEI, Short %, Date
                df.columns = ['Company Name', 'LEI', 'Short %', 'Date']
                
                for _, row in df.iterrows():
                    try:
                        company_name = str(row['Company Name']).strip()
                        lei = str(row['LEI']).strip()
                        short_pct = pd.to_numeric(row['Short %'], errors='coerce')
                        position_date = str(row['Date']).strip()
                        
                        # Skip invalid rows
                        if not company_name or company_name == 'nan' or pd.isna(short_pct) or short_pct <= 0:
                            continue
                        
                        # Determine threshold - aggregated file includes positions from 0.1%
                        threshold = "0.1%" if file_type == 'aggregated' else "0.5%"
                        
                        positions.append(ShortPosition(
                            ticker=lei,  # Use LEI as ticker for now
                            company_name=company_name,
                            position_holder="Multiple (aggregated)",
                            position_percentage=float(short_pct),
                            position_date=position_date,
                            threshold_crossed=threshold,
                            market='SE'
                        ))
                        
                    except (ValueError, KeyError, AttributeError) as e:
                        logger.debug(f"Error parsing aggregated row: {e}")
                        continue
                
                logger.info(f"✓ Parsed {len(positions)} companies from {file_type} file")
                
            elif len(df.columns) == 6:
                # Detailed format with individual position holders: need to aggregate by company
                df.columns = ['Position Holder', 'Company Name', 'ISIN', 'Short %', 'Date', 'Comment']
                
                # Convert Short % to numeric
                df['Short %'] = pd.to_numeric(df['Short %'], errors='coerce')
                
                # Group by company and ISIN to aggregate all position holders
                company_groups = df.groupby(['Company Name', 'ISIN'], dropna=True)
                
                # Determine threshold based on file type
                threshold = "0.5%" if file_type != 'aggregated' else "0.1%"
                
                # Convert to ShortPosition objects with individual holder details
                for (company_name, isin), group in company_groups:
                    try:
                        company_name = str(company_name).strip()
                        isin = str(isin).strip()
                        
                        # Skip invalid rows
                        if not company_name or company_name == 'nan':
                            continue
                        
                        # Calculate total short percentage
                        total_short_pct = float(group['Short %'].sum())
                        
                        if total_short_pct <= 0:
                            continue
                        
                        # Extract individual holders
                        individual_holders = []
                        for _, holder_row in group.iterrows():
                            holder_name = str(holder_row['Position Holder']).strip()
                            holder_pct = float(holder_row['Short %'])
                            holder_date = str(holder_row['Date']).strip()
                            
                            if holder_name and holder_name != 'nan' and holder_pct > 0:
                                individual_holders.append(PositionHolder(
                                    holder_name=holder_name,
                                    position_percentage=holder_pct,
                                    position_date=holder_date
                                ))
                        
                        # Sort holders by position size (largest first)
                        individual_holders.sort(key=lambda h: h.position_percentage, reverse=True)
                        
                        # Use most recent date
                        position_date = str(group['Date'].iloc[0]).strip()
                        
                        # Create summary string
                        holder_info = f"{len(individual_holders)} holders"
                        if individual_holders:
                            top_holder = individual_holders[0]
                            holder_info = f"{len(individual_holders)} holders (largest: {top_holder.holder_name} {top_holder.position_percentage:.2f}%)"
                        
                        positions.append(ShortPosition(
                            ticker=isin,
                            company_name=company_name,
                            position_holder=holder_info,
                            position_percentage=total_short_pct,
                            position_date=position_date,
                            threshold_crossed=threshold,
                            market='SE',
                            individual_holders=individual_holders
                        ))
                        
                    except (ValueError, KeyError, AttributeError) as e:
                        logger.debug(f"Error parsing grouped row: {e}")
                        continue
                        
                logger.info(f"✓ Parsed {len(positions)} companies from {file_type} file (aggregated from {len(df)} individual positions)")
            else:
                logger.warning(f"Unexpected DataFrame structure with {len(df.columns)} columns")
            
        except Exception as e:
            logger.error(f"Error parsing {file_type} DataFrame: {e}")
            
        return positions

    def fetch_swedish_short_positions(self) -> List[ShortPosition]:
        """
        Fetch short positions from Finansinspektionen (Swedish FSA).
        
        Strategy:
        1. Fetch current file (individual holders, >0.5%, most recent)
        2. Fetch aggregated file (total per company, >0.1%, includes historical)
        3. Merge: Use aggregated totals, but add holder details from current file
        
        This gives us both the complete total percentage AND individual holder breakdown.
        """
        positions = []
        
        try:
            logger.info("Fetching Swedish short selling data from Finansinspektionen...")
            
            # Fetch current positions with individual holder details
            df_current = self.fetch_fi_ods_file('current')
            current_positions = []
            if df_current is not None:
                current_positions = self.parse_fi_dataframe(df_current, 'current')
                logger.info(f"Current file: {len(current_positions)} companies with holder details")
            
            # Fetch aggregated positions (complete totals including historical)
            # Try with default timeout first, then retry with longer timeout if needed
            df_aggregated = self.fetch_fi_ods_file('aggregated')
            
            # Retry with longer timeout if first attempt failed
            if df_aggregated is None:
                logger.info("Retrying aggregated file with extended timeout (90s)...")
                df_aggregated = self.fetch_fi_ods_file('aggregated', timeout=90)
            
            aggregated_positions = []
            if df_aggregated is not None:
                aggregated_positions = self.parse_fi_dataframe(df_aggregated, 'aggregated')
                logger.info(f"Aggregated file: {len(aggregated_positions)} companies with complete totals")
                
                # Cache successful aggregated data for future fallback
                self._cache_aggregated_positions(aggregated_positions)
            
            # Merge strategy: Use aggregated as base (has complete totals)
            # Then enhance with holder details from current file
            if aggregated_positions:
                # Create lookup for current positions by company name
                current_lookup = {pos.company_name: pos for pos in current_positions}
                
                for agg_pos in aggregated_positions:
                    # Check if we have detailed holder info from current file
                    if agg_pos.company_name in current_lookup:
                        current_pos = current_lookup[agg_pos.company_name]
                        
                        # Use aggregated total (more complete), but add holder details
                        agg_pos.individual_holders = current_pos.individual_holders
                        
                        # Update position_holder summary to include holder count
                        if current_pos.individual_holders:
                            top_holder = current_pos.individual_holders[0]
                            agg_pos.position_holder = f"{len(current_pos.individual_holders)} holders (top: {top_holder.holder_name} {top_holder.position_percentage:.2f}%)"
                        else:
                            agg_pos.position_holder = f"{len(current_pos.individual_holders)} holders"
                    
                    positions.append(agg_pos)
                
                logger.info(f"✓ Merged data: {len(positions)} total companies")
                
                # Count how many have holder details
                with_holders = sum(1 for p in positions if p.individual_holders)
                logger.info(f"  - {with_holders} companies have individual holder details")
                logger.info(f"  - {len(positions) - with_holders} companies only have aggregated totals")
                
                return positions
            
            # Fallback: Try to use cached aggregated data
            cached_positions = self._load_cached_aggregated_positions()
            if cached_positions:
                logger.warning(f"Using cached aggregated data ({len(cached_positions)} positions) - FI.se may be down")
                # Enhance cached positions with current holder details if available
                current_lookup = {pos.company_name: pos for pos in current_positions}
                for pos in cached_positions:
                    if pos.company_name in current_lookup:
                        current_pos = current_lookup[pos.company_name]
                        pos.individual_holders = current_pos.individual_holders
                return cached_positions
            
            # Final fallback: if no cached data, use current only
            if current_positions:
                logger.warning("Using current positions only (no aggregated data available, no cache)")
                return current_positions
            
            # Final fallback to HTML scraping
            logger.info("Falling back to HTML scraping...")
            
            # FI's short position register (Swedish version has the data table)
            url = "https://www.fi.se/sv/vara-register/blankningsregistret/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find the data table
                table = soup.find('table')
                
                if table:
                    rows = table.find_all('tr')
                    logger.info(f"Found table with {len(rows)} rows")
                    
                    # Skip header row
                    for row in rows[1:]:
                        cells = row.find_all('td')
                        if len(cells) >= 4:
                            try:
                                company_name = cells[0].get_text(strip=True)
                                lei_code = cells[1].get_text(strip=True)
                                position_date = cells[2].get_text(strip=True)
                                total_short_pct = cells[3].get_text(strip=True)
                                
                                # Convert percentage string to float
                                # Format is "2,56" -> 2.56
                                short_pct = float(total_short_pct.replace(',', '.'))
                                
                                # Try to find ISIN from LEI or company name
                                # For now, we'll store the company name and match later
                                positions.append(ShortPosition(
                                    ticker=lei_code,  # We'll use LEI as temporary identifier
                                    company_name=company_name,
                                    position_holder="Multiple (aggregated)",  # FI shows total
                                    position_percentage=short_pct,
                                    position_date=position_date,
                                    threshold_crossed="0.5%",
                                    market='SE'
                                ))
                            except (ValueError, IndexError) as e:
                                logger.debug(f"Error parsing row: {e}")
                                continue
                    
                    logger.info(f"✓ Fetched {len(positions)} Swedish short positions")
                else:
                    logger.warning("No data table found on FI page")
            else:
                logger.warning(f"Failed to access Swedish FSA data: HTTP {response.status_code}")
            
        except ImportError:
            logger.error("BeautifulSoup4 not available - cannot parse FI data")
            logger.info("Install with: pip install beautifulsoup4")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error fetching Swedish short positions: {e}")
        except Exception as e:
            logger.error(f"Error fetching Swedish short positions: {e}")
            
        return positions
    
    def fetch_finnish_short_positions(self) -> List[ShortPosition]:
        """
        Fetch short positions from Finanssivalvonta (Finnish FSA).
        
        Finanssivalvonta publishes net short position data in their public register.
        """
        positions = []
        
        try:
            logger.info("Fetching Finnish short selling data from Finanssivalvonta...")
            
            # Finanssivalvonta's short position register
            url = "https://www.finanssivalvonta.fi/en/capital-markets/short-selling/net-short-positions/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Similar to Swedish implementation - requires parsing their data format
                logger.info("Finnish FSA page accessed, data parsing not yet implemented")
                logger.info("Using alternative data sources for Finnish stocks")
            else:
                logger.warning(f"Failed to access Finnish FSA data: HTTP {response.status_code}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching Finnish short positions: {e}")
        except Exception as e:
            logger.error(f"Error fetching Finnish short positions: {e}")
            
        return positions
    
    def fetch_esma_short_positions(self) -> List[ShortPosition]:
        """
        Fetch short positions from ESMA (European Securities and Markets Authority).
        
        ESMA maintains a central register of all short positions across EU.
        Note: ESMA doesn't provide a simple API, so this attempts to scrape their data.
        """
        positions = []
        
        try:
            logger.info("Checking ESMA short selling register...")
            
            # ESMA provides data files - try to get the latest
            # They publish daily Excel files with short positions
            base_url = "https://registers.esma.europa.eu/publication/"
            
            # For now, return empty and rely on national sources
            # A full implementation would require scraping or downloading Excel files
            logger.info("ESMA requires web scraping - using national regulators instead")
            
        except Exception as e:
            logger.error(f"Error accessing ESMA data: {e}")
            
        return positions
    
    def fetch_alternative_short_data(self, tickers: List[str]) -> Dict[str, float]:
        """
        Fetch short interest data from yfinance.
        
        This provides supplementary data including:
        - Short ratio (days to cover)
        - Short % of float
        - Short % of shares outstanding
        """
        short_data = {}
        
        try:
            import yfinance as yf
            
            logger.info(f"Fetching short interest data for {len(tickers)} stocks...")
            
            for ticker in tickers:
                try:
                    logger.debug(f"Fetching data for {ticker}...")
                    stock = yf.Ticker(ticker)
                    info = stock.info
                    
                    # Extract short interest metrics
                    short_ratio = info.get('shortRatio', None)
                    short_percent = info.get('shortPercentOfFloat', None)
                    shares_short = info.get('sharesShort', None)
                    shares_short_prior = info.get('sharesShortPriorMonth', None)
                    
                    # Only store if we have at least some data
                    if any([short_ratio, short_percent, shares_short]):
                        short_data[ticker] = {
                            'short_ratio': short_ratio,
                            'short_percent_of_float': short_percent,
                            'shares_short': shares_short,
                            'shares_short_prior_month': shares_short_prior,
                            'last_updated': datetime.now().isoformat()
                        }
                        
                        logger.info(f"✓ Short data found for {ticker}: "
                                  f"Ratio={short_ratio}, Float%={short_percent}")
                    else:
                        logger.debug(f"No short data available for {ticker}")
                        
                except Exception as e:
                    logger.debug(f"Failed to fetch short data for {ticker}: {e}")
                    
            logger.info(f"Successfully fetched short data for {len(short_data)}/{len(tickers)} stocks")
                    
        except ImportError:
            logger.error("yfinance not available - cannot fetch short selling data")
        except Exception as e:
            logger.error(f"Error fetching alternative short data: {e}")
            
        return short_data
    
    def needs_update(self) -> bool:
        """Check if short selling data needs to be updated."""
        try:
            if not self.short_positions_file.exists():
                return True
                
            # Check if data is older than 24 hours
            file_stat = self.short_positions_file.stat()
            file_age = datetime.now().timestamp() - file_stat.st_mtime
            
            # Update if older than 24 hours (86400 seconds)
            if file_age > 86400:
                logger.info("Short selling data is older than 24 hours, needs update")
                return True
            
            # Check if portfolio has new Nordic stocks not in the data
            with open(self.short_positions_file) as f:
                data = json.load(f)
                
            current_tickers = set(self.get_portfolio_tickers().keys())
            tracked_tickers = set(data.get('portfolio_tickers', {}).keys())
            
            if current_tickers != tracked_tickers:
                logger.info("Portfolio has changed, short selling data needs update")
                return True
                
            logger.info("Short selling data is current")
            return False
            
        except Exception as e:
            logger.warning(f"Error checking short selling data freshness: {e}")
            return True  # When in doubt, update
    
    def update_short_positions(self, force: bool = False) -> Dict[str, any]:
        """
        Update short selling positions for all portfolio stocks.
        
        Args:
            force: If True, force update even if data is current (bypass 24-hour check)
        
        Returns:
            Dict with keys:
            - 'success': bool - whether operation completed successfully
            - 'updated': bool - whether data was actually updated
            - 'message': str - status message
            - 'stats': dict - statistics about the update (if updated)
        """
        try:
            # Try to fetch from remote server first
            try:
                from short_selling.remote_short_data import load_remote_config, RemoteShortDataFetcher
                
                # Try config/remote_config.json first, then remote_config.json
                import os
                config_path = 'config/remote_config.json' if os.path.exists('config/remote_config.json') else 'remote_config.json'
                config = load_remote_config(config_path)
                fetcher = RemoteShortDataFetcher(config)
                success, remote_data = fetcher.fetch_data(force_refresh=force)
                
                if success and remote_data:
                    logger.info("Successfully fetched data from remote server")
                    # Use the remote data to update local file
                    return self._update_from_remote_data(remote_data, force)
                else:
                    logger.warning("Remote fetch failed, falling back to direct regulator fetch")
            except Exception as e:
                logger.warning(f"Could not fetch from remote server: {e}, falling back to direct fetch")
            
            # Fallback: Fetch directly from regulators (original behavior)
            # Check if update is needed (unless force=True)
            if not force and not self.needs_update():
                logger.info("Data is current, no update needed")
                return {
                    'success': True,
                    'updated': False,
                    'message': 'Data is already current (updated within last 24 hours)',
                    'stats': {}
                }
            
            if force:
                logger.info("Force update requested, bypassing freshness check and fetching directly from regulators")
                
            portfolio_tickers = self.get_portfolio_tickers()
            
            if not portfolio_tickers:
                logger.info("No Nordic tickers found in portfolio")
                return {
                    'success': True,
                    'updated': False,
                    'message': 'No Nordic stocks in portfolio to track',
                    'stats': {}
                }
                
            logger.info(f"Updating short positions for {len(portfolio_tickers)} Nordic stocks...")
            
            all_positions = []
            
            # Try ESMA register first (comprehensive EU source)
            esma_positions = self.fetch_esma_short_positions()
            all_positions.extend(esma_positions)
            
            # Fetch from national regulators if ESMA failed or as supplement
            if len(esma_positions) == 0:
                logger.info("ESMA fetch unsuccessful, trying national regulators...")
                all_positions.extend(self.fetch_swedish_short_positions())
                all_positions.extend(self.fetch_finnish_short_positions())
            
            # Get alternative data for all tickers
            tickers = list(portfolio_tickers.values())
            alternative_data = self.fetch_alternative_short_data(tickers)
            
            # Build ISIN mapping for future use
            isin_mapping = self.build_isin_mapping(tickers)
            
            # Match portfolio stocks with short positions
            portfolio_matches = self.match_portfolio_with_short_data(
                all_positions, portfolio_tickers, isin_mapping
            )
            
            # Save positions data
            positions_data = {
                'last_updated': datetime.now().isoformat(),
                'official_positions': [
                    {
                        'ticker': pos.ticker,
                        'company_name': pos.company_name,
                        'position_holder': pos.position_holder,
                        'position_percentage': pos.position_percentage,
                        'position_date': pos.position_date,
                        'market': pos.market,
                        'threshold_crossed': pos.threshold_crossed,
                        'individual_holders': [
                            {
                                'holder_name': h.holder_name,
                                'position_percentage': h.position_percentage,
                                'position_date': h.position_date
                            }
                            for h in (pos.individual_holders or [])
                        ] if pos.individual_holders else []
                    }
                    for pos in all_positions
                ],
                'alternative_data': alternative_data,
                'portfolio_tickers': portfolio_tickers,
                'isin_mapping': isin_mapping,
                'portfolio_matches': portfolio_matches
            }
            
            # Ensure directory exists
            self.portfolio_path.mkdir(exist_ok=True)
            
            with open(self.short_positions_file, 'w') as f:
                json.dump(positions_data, f, indent=2)
                
            logger.info(f"Short positions updated: {len(all_positions)} official positions, "
                       f"{len(alternative_data)} alternative data points")
            
            # Count positions with individual holder details
            positions_with_holders = sum(1 for pos in all_positions if pos.individual_holders)
            
            return {
                'success': True,
                'updated': True,
                'message': 'Short selling data updated successfully',
                'stats': {
                    'total_positions': len(all_positions),
                    'positions_with_holders': positions_with_holders,
                    'alternative_data_count': len(alternative_data),
                    'portfolio_matches': len(portfolio_matches),
                    'nordic_stocks': len(portfolio_tickers)
                }
            }
            
        except Exception as e:
            logger.error(f"Error updating short positions: {e}")
            return {
                'success': False,
                'updated': False,
                'message': f'Error: {str(e)}',
                'stats': {}
            }
    
    def _update_from_remote_data(self, remote_data: Dict, force: bool) -> Dict[str, any]:
        """
        Update local data from remote server data.
        
        Args:
            remote_data: Data fetched from remote server
            force: Whether this was a forced update
            
        Returns:
            Dict with update status and stats
        """
        try:
            # Remote data should contain 'positions' and 'metadata'
            positions_list = remote_data.get('positions', [])
            metadata = remote_data.get('metadata', {})
            last_updated = remote_data.get('last_updated', datetime.now().isoformat())
            
            # Convert positions list to ShortPosition objects
            all_positions = []
            for pos_data in positions_list:
                try:
                    # Handle individual holders
                    individual_holders = []
                    if 'individual_holders' in pos_data:
                        for holder_data in pos_data['individual_holders']:
                            individual_holders.append(PositionHolder(
                                holder_name=holder_data['holder_name'],
                                position_percentage=holder_data['position_percentage'],
                                position_date=holder_data['position_date']
                            ))
                    
                    position = ShortPosition(
                        ticker=pos_data['ticker'],
                        company_name=pos_data['company_name'],
                        position_holder=pos_data['position_holder'],
                        position_percentage=pos_data['position_percentage'],
                        position_date=pos_data['position_date'],
                        market=pos_data.get('market', 'SE'),
                        threshold_crossed=pos_data.get('threshold_crossed', ''),
                        individual_holders=individual_holders if individual_holders else None
                    )
                    all_positions.append(position)
                except Exception as e:
                    logger.warning(f"Could not parse position data: {e}")
                    continue
            
            # Get portfolio tickers for matching
            portfolio_tickers = self.get_portfolio_tickers()
            
            # Build ISIN mapping
            tickers = list(portfolio_tickers.values())
            isin_mapping = self.build_isin_mapping(tickers)
            
            # Match portfolio stocks with short positions
            portfolio_matches = self.match_portfolio_with_short_data(
                all_positions, portfolio_tickers, isin_mapping
            )
            
            # Get alternative data if available
            alternative_data = remote_data.get('alternative_data', {})
            
            # Save positions data
            positions_data = {
                'last_updated': last_updated,
                'official_positions': [
                    {
                        'ticker': pos.ticker,
                        'company_name': pos.company_name,
                        'position_holder': pos.position_holder,
                        'position_percentage': pos.position_percentage,
                        'position_date': pos.position_date,
                        'market': pos.market,
                        'threshold_crossed': pos.threshold_crossed,
                        'individual_holders': [
                            {
                                'holder_name': h.holder_name,
                                'position_percentage': h.position_percentage,
                                'position_date': h.position_date
                            }
                            for h in (pos.individual_holders or [])
                        ] if pos.individual_holders else []
                    }
                    for pos in all_positions
                ],
                'alternative_data': alternative_data,
                'portfolio_tickers': portfolio_tickers,
                'isin_mapping': isin_mapping,
                'portfolio_matches': portfolio_matches
            }
            
            # Ensure directory exists
            self.portfolio_path.mkdir(exist_ok=True)
            
            with open(self.short_positions_file, 'w') as f:
                json.dump(positions_data, f, indent=2)
                
            logger.info(f"Updated from remote: {len(all_positions)} positions, "
                       f"{len(portfolio_matches)} portfolio matches")
            
            # Count positions with individual holder details
            positions_with_holders = sum(1 for pos in all_positions if pos.individual_holders)
            
            return {
                'success': True,
                'updated': True,
                'message': 'Short selling data updated from remote server',
                'stats': {
                    'total_positions': len(all_positions),
                    'positions_with_holders': positions_with_holders,
                    'alternative_data_count': len(alternative_data),
                    'portfolio_matches': len(portfolio_matches),
                    'nordic_stocks': len(portfolio_tickers)
                }
            }
            
        except Exception as e:
            logger.error(f"Error updating from remote data: {e}")
            return {
                'success': False,
                'updated': False,
                'message': f'Error processing remote data: {str(e)}',
                'stats': {}
            }
    
    def match_portfolio_with_short_data(self, positions: List[ShortPosition], 
                                        portfolio_tickers: Dict[str, str],
                                        isin_mapping: Dict[str, str]) -> Dict[str, Dict]:
        """
        Match portfolio stocks with short selling positions.
        Returns dict mapping ticker -> short position data.
        """
        matches = {}
        
        # Create lookup structures
        # Company name normalization for matching
        def normalize_name(name: str) -> str:
            """Normalize company name for matching."""
            name = name.lower()
            # Remove common suffixes
            for suffix in [' ab', ' (publ)', ' aktiebolag', ' oyj', ' asa', ' a/s', ' ltd', ' plc']:
                name = name.replace(suffix, '')
            # Remove extra spaces
            name = ' '.join(name.split())
            return name.strip()
        
        def get_name_variations(name: str) -> set:
            """Get various name forms for matching."""
            variations = set()
            normalized = normalize_name(name)
            variations.add(normalized)
            
            # Remove hyphens and add both with/without spaces
            no_hyphen = normalized.replace('-', ' ')
            variations.add(no_hyphen)
            variations.add(normalized.replace('-', ''))
            
            # Remove share class suffixes (-a, -b, sdb) BEFORE removing hyphens
            base = normalized
            for suffix in ['-a', '-b', ' a', ' b', 'sdb', '-sdb']:
                base = base.replace(suffix, '')
            base = base.strip()
            variations.add(base)
            variations.add(base.replace('-', ' '))
            variations.add(base.replace('-', ''))
            
            # Add first word for company name matching
            words = normalized.split()
            if len(words) > 0:
                variations.add(words[0])
            
            # For "Aktiebolaget X" pattern, also add "X" alone
            # This helps match "Aktiebolaget Electrolux" to "electrolux-b"
            if len(words) >= 2:
                if words[0] in ['aktiebolaget', 'ab']:
                    # Add the actual company name without the legal form
                    variations.add(words[1])
                    if len(words) > 2:
                        # "Aktiebolaget Svenska Handelsbanken" -> also add "svenska handelsbanken"
                        variations.add(' '.join(words[1:]))
            
            # For multi-word hyphenated names, add without hyphens
            if '-' in normalized:
                words_no_hyphen = normalized.replace('-', ' ').split()
                if len(words_no_hyphen) > 1:
                    # "assa-abloy" -> "assa abloy"
                    variations.add(' '.join(words_no_hyphen))
            
            # Special handling for common abbreviations and name variations
            abbrev_map = {
                'handelsbanken': ['svenska handelsbanken'],
                'hm': ['hennes mauritz', 'h m', 'hms networks'],
                'h m': ['hennes mauritz', 'hms networks'],
                'ericsson': ['telefonaktiebolaget lm ericsson', 'lm ericsson'],
                'atlas copco': ['atlas copco aktiebolag'],
                'atlascopco': ['atlas copco aktiebolag', 'atlas copco'],
                'autoliv': ['autoliv inc'],
                'assa abloy': ['assa abloy'],
                'assaabloy': ['assa abloy'],
                'skf': ['aktiebolaget skf'],
                'sca': ['svenska cellulosa aktiebolaget sca', 'svenska cellulosa'],
                'seb': ['skandinaviska enskilda banken'],
                'sbb': ['samhällsbyggnadsbolaget', 'samhällsbyggnadsbolaget i norden'],
                'finnair': ['finnair oyj'],
                'norwegian': ['norwegian air shuttle'],
                'dfds': ['dfds a/s'],
                'viscaria': ['gruvaktiebolaget viscaria'],
                'volvocar': ['volvo car'],  # Volvo Cars (separate company)
                # Note: 'volvo' alone now only matches Volvo Group (Aktiebolaget Volvo)
                # Do NOT map 'volvo' to 'volvo car' - they are different companies!
            }
            
            # Add mapped variations - use word boundary matching to avoid false matches
            # e.g., 'sca' should not match 'viscaria' just because 'sca' is a substring
            name_words = set(normalized.split() + no_hyphen.split() + base.split())
            name_words.add(normalized)
            name_words.add(no_hyphen)
            name_words.add(base)
            
            for key, values in abbrev_map.items():
                # Only match if key is a complete word or the entire name
                if key in name_words:
                    for value in values:
                        variations.add(value)
                        variations.add(normalize_name(value))
            
            return variations
        
        # Build portfolio lookup by name variations
        # Allow multiple tickers to have same variation (for A/B shares)
        portfolio_lookup = {}  # normalized_name -> list of (ticker_name, ticker_symbol)
        for ticker_name, ticker_symbol in portfolio_tickers.items():
            variations = get_name_variations(ticker_name)
            for var in variations:
                if len(var) > 2:  # Only use variations longer than 2 chars
                    if var not in portfolio_lookup:
                        portfolio_lookup[var] = []
                    portfolio_lookup[var].append((ticker_name, ticker_symbol))
        
        # Try to match each position
        matched_positions = {}  # ticker -> match_info
        
        for pos in positions:
            company_variations = get_name_variations(pos.company_name)
            
            # Try to find a match with any variation
            potential_matches = []
            
            for company_var in company_variations:
                if company_var in portfolio_lookup:
                    for ticker_name, ticker in portfolio_lookup[company_var]:
                        # Skip if already matched (unless this is a better match)
                        
                        # Calculate match quality
                        portfolio_norm = normalize_name(ticker_name)
                        company_norm = normalize_name(pos.company_name)
                        
                        if portfolio_norm == company_norm:
                            quality = 'exact'
                            score = 100
                        elif company_var == company_norm:
                            quality = 'normalized'
                            score = 90
                        elif len(company_var) > 10:  # Long match is better
                            quality = 'long_variation'
                            score = 85
                        else:
                            quality = 'variation'
                            score = 80
                        
                        # Prefer main company over subsidiaries
                        # "Aktiebolaget Electrolux" over "Electrolux Professional"
                        company_words = company_norm.split()
                        portfolio_words = portfolio_norm.split()
                        
                        # If company name is "aktiebolaget X" and portfolio contains "x"
                        # This is likely the main company (e.g., Aktiebolaget Electrolux for electrolux-b)
                        if len(company_words) == 2 and company_words[0] == 'aktiebolaget':
                            # Check if the second word (company name) matches portfolio
                            company_base = company_words[1]
                            # Remove share class suffixes from portfolio for comparison
                            portfolio_base = portfolio_norm.replace('-a', '').replace('-b', '').replace(' a', '').replace(' b', '').strip()
                            
                            if company_base == portfolio_base or company_base in portfolio_base:
                                score += 15  # Strong bonus for main company pattern
                        
                        # Penalize if company has extra descriptors (professional, group, holding, etc.)
                        # These indicate subsidiaries or divisions
                        descriptors = ['professional', 'group', 'holding', 'international', 'systems', 'networks']
                        if any(desc in company_norm for desc in descriptors):
                            score -= 10  # Stronger penalty for subsidiaries
                        
                        # Prefer shorter company names (likely parent companies)
                        company_word_count = len(company_words)
                        if company_word_count == 1:
                            score += 5  # Bonus for single-word company names
                        elif company_word_count == 2:
                            score += 3  # Smaller bonus for two-word names
                        
                        # Bonus if company name starts with the search term
                        if company_norm.startswith(company_var) or company_norm.endswith(company_var):
                            score += 2
                        
                        potential_matches.append((ticker, {
                            'company_name': pos.company_name,
                            'short_percentage': pos.position_percentage,
                            'position_date': pos.position_date,
                            'position_holder': pos.position_holder,
                            'market': pos.market,
                            'match_quality': quality,
                            'match_score': score
                        }))
            
            # For each potential match, assign if it's the best match for that ticker
            for ticker, match_info in potential_matches:
                if ticker not in matched_positions or match_info['match_score'] > matched_positions[ticker]['match_score']:
                    matched_positions[ticker] = match_info
        
        logger.info(f"Matched {len(matched_positions)} portfolio stocks with short position data")
        
        # Show match quality breakdown
        exact = sum(1 for m in matched_positions.values() if m['match_quality'] == 'exact')
        normalized = sum(1 for m in matched_positions.values() if m['match_quality'] == 'normalized')
        variation = sum(1 for m in matched_positions.values() if m['match_quality'] == 'variation')
        logger.info(f"Match quality: {exact} exact, {normalized} normalized, {variation} variation")
        
        return matched_positions
    
    def get_short_data_for_stock(self, ticker: str) -> Optional[Dict]:
        """Get short selling data for a specific stock."""
        try:
            if not self.short_positions_file.exists():
                return None
                
            with open(self.short_positions_file) as f:
                data = json.load(f)
            
            # Check portfolio matches first
            portfolio_matches = data.get('portfolio_matches', {})
            if ticker in portfolio_matches:
                match_data = portfolio_matches[ticker]
                
                # Try to enhance with individual holder data from official_positions
                # Match by company name to find the full position data
                company_name = match_data.get('company_name', '')
                for pos in data.get('official_positions', []):
                    if pos.get('company_name') == company_name:
                        # Merge: use match_data as base, but add individual_holders from pos
                        enhanced_data = match_data.copy()
                        enhanced_data['individual_holders'] = pos.get('individual_holders', [])
                        enhanced_data['threshold_crossed'] = pos.get('threshold_crossed', '0.5%')
                        return {
                            'type': 'official',
                            'data': enhanced_data
                        }
                
                # If no match found in official_positions, return match_data as is
                return {
                    'type': 'official',
                    'data': match_data
                }
                
            # Check official positions by ticker/LEI
            for pos in data.get('official_positions', []):
                if pos['ticker'] == ticker:
                    return {
                        'type': 'official',
                        'data': pos
                    }
                    
            # Check alternative data
            alt_data = data.get('alternative_data', {})
            if ticker in alt_data:
                return {
                    'type': 'alternative',
                    'data': alt_data[ticker]
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting short data for {ticker}: {e}")
            return None
    
    def get_portfolio_short_summary(self) -> Dict:
        """Get a summary of short selling activity for the entire portfolio."""
        try:
            if not self.short_positions_file.exists():
                return {'error': 'No short selling data available'}
                
            with open(self.short_positions_file) as f:
                data = json.load(f)
                
            portfolio_tickers = data.get('portfolio_tickers', {})
            portfolio_matches = data.get('portfolio_matches', {})
            official_positions = data.get('official_positions', [])
            alternative_data = data.get('alternative_data', {})
            
            summary = {
                'last_updated': data.get('last_updated'),
                'total_stocks_tracked': len(portfolio_tickers),
                'stocks_with_short_data': len(portfolio_matches),
                'stocks_with_alternative_data': len(alternative_data),
                'high_short_interest_stocks': [],  # >5% short interest
                'portfolio_short_positions': []
            }
            
            # Analyze portfolio matches
            for ticker, short_data in portfolio_matches.items():
                short_pct = short_data['short_percentage']
                
                pos_info = {
                    'ticker': ticker,
                    'company': short_data['company_name'],
                    'percentage': short_pct,
                    'date': short_data['position_date']
                }
                
                summary['portfolio_short_positions'].append(pos_info)
                
                # Flag high short interest (>5%)
                if short_pct > 5.0:
                    summary['high_short_interest_stocks'].append(pos_info)
            
            # Sort by percentage
            summary['high_short_interest_stocks'].sort(
                key=lambda x: x['percentage'], reverse=True
            )
            summary['portfolio_short_positions'].sort(
                key=lambda x: x['percentage'], reverse=True
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating short summary: {e}")
            return {'error': str(e)}
    
    def get_positions_by_holder(self) -> Dict[str, List[Dict]]:
        """
        Get all positions grouped by holder name.
        
        Returns:
            Dict mapping holder_name -> list of positions with company details
            {
                'JPMorgan Chase Bank, National Association, London Branch': [
                    {
                        'company_name': 'Elekta AB (publ)',
                        'ticker': 'EKTA-B.ST',
                        'position_percentage': 1.37,
                        'position_date': '2024-01-15',
                        'total_company_short': 13.04  # Total short % for the company
                    },
                    ...
                ]
            }
        """
        try:
            if not self.short_positions_file.exists():
                return {}
                
            with open(self.short_positions_file) as f:
                data = json.load(f)
            
            official_positions = data.get('official_positions', [])
            
            # Build holder -> positions mapping
            holder_positions = {}
            
            for pos in official_positions:
                company_name = pos.get('company_name', 'Unknown')
                ticker = pos.get('ticker', 'N/A')
                total_short_pct = pos.get('position_percentage', 0)
                
                individual_holders = pos.get('individual_holders', [])
                
                for holder in individual_holders:
                    holder_name = holder.get('holder_name', 'Unknown')
                    holder_pct = holder.get('position_percentage', 0)
                    holder_date = holder.get('position_date', 'N/A')
                    
                    if holder_name not in holder_positions:
                        holder_positions[holder_name] = []
                    
                    holder_positions[holder_name].append({
                        'company_name': company_name,
                        'ticker': ticker,
                        'position_percentage': holder_pct,
                        'position_date': holder_date,
                        'total_company_short': total_short_pct
                    })
            
            # Sort each holder's positions by percentage (descending)
            for holder_name in holder_positions:
                holder_positions[holder_name].sort(
                    key=lambda x: x['position_percentage'], 
                    reverse=True
                )
            
            logger.info(f"Found {len(holder_positions)} unique position holders")
            
            return holder_positions
            
        except Exception as e:
            logger.error(f"Error getting positions by holder: {e}")
            return {}


def main():
    """Command line interface for short selling tracker."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Track short selling positions for Nordic stocks')
    parser.add_argument('--update', action='store_true', help='Update short positions data')
    parser.add_argument('--summary', action='store_true', help='Show portfolio short selling summary')
    parser.add_argument('--ticker', type=str, help='Get short data for specific ticker')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    tracker = ShortSellingTracker()
    
    if args.update:
        success = tracker.update_short_positions()
        if success:
            print("✅ Short positions updated successfully")
        else:
            print("❌ Failed to update short positions")
            
    elif args.summary:
        summary = tracker.get_portfolio_short_summary()
        print("\n📊 Portfolio Short Selling Summary")
        print("=" * 60)
        print(f"Last updated: {summary.get('last_updated', 'N/A')}")
        print(f"Total portfolio stocks: {summary.get('total_stocks_tracked', 0)}")
        print(f"Stocks with short data: {summary.get('stocks_with_short_data', 0)}")
        
        if summary.get('portfolio_short_positions'):
            print(f"\n📈 All Portfolio Short Positions ({len(summary['portfolio_short_positions'])}):")
            print("-" * 60)
            for stock in summary['portfolio_short_positions'][:15]:
                print(f"  {stock['ticker']:15} {stock['company']:30} {stock['percentage']:5.2f}%")
            
            if len(summary['portfolio_short_positions']) > 15:
                print(f"  ... and {len(summary['portfolio_short_positions']) - 15} more")
        
        if summary.get('high_short_interest_stocks'):
            print(f"\n⚠️  High Short Interest (>5%):")
            print("-" * 60)
            for stock in summary['high_short_interest_stocks']:
                print(f"  {stock['ticker']:15} {stock['company']:30} {stock['percentage']:5.2f}%")
                
    elif args.ticker:
        data = tracker.get_short_data_for_stock(args.ticker)
        if data:
            print(f"\n📈 Short Data for {args.ticker}")
            print("=" * 30)
            print(f"Type: {data['type']}")
            for key, value in data['data'].items():
                print(f"{key}: {value}")
        else:
            print(f"No short selling data found for {args.ticker}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()