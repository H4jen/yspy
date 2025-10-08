#!/usr/bin/env python3
"""
Short Selling Data Tracker for Nordic Markets

Fetches and tracks short selling positions for stocks in the portfolio.
Integrates with Finansinspektionen and other Nordic regulatory sources.
"""

import requests
import pandas as pd
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

@dataclass
class ShortPosition:
    """Represents a short selling position."""
    ticker: str
    company_name: str
    position_holder: str
    position_percentage: float
    position_date: str
    threshold_crossed: str
    market: str  # 'SE' for Sweden, 'FI' for Finland, etc.

class ShortSellingTracker:
    """Tracks short selling positions for Nordic markets."""
    
    def __init__(self, portfolio_path: str = "portfolio"):
        self.portfolio_path = Path(portfolio_path)
        self.short_positions_file = self.portfolio_path / "short_positions.json"
        self.cache_file = self.portfolio_path / "short_selling_cache.json"
        
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
            from nordic_isin_mapping import get_isin
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
    
    def fetch_swedish_short_positions(self) -> List[ShortPosition]:
        """
        Fetch short positions from Finansinspektionen (Swedish FSA).
        
        FI publishes short position data on their website in an HTML table.
        """
        positions = []
        
        try:
            logger.info("Fetching Swedish short selling data from Finansinspektionen...")
            
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
    
    def update_short_positions(self) -> bool:
        """
        Update short selling positions for all portfolio stocks.
        Returns True if update was performed, False if data was already current.
        """
        try:
            # Check if update is needed
            if not self.needs_update():
                return False
                
            portfolio_tickers = self.get_portfolio_tickers()
            
            if not portfolio_tickers:
                logger.info("No Nordic tickers found in portfolio")
                return False
                
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
                        'market': pos.market
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
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating short positions: {e}")
            return False
    
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
                'finnair': ['finnair oyj'],
                'norwegian': ['norwegian air shuttle'],
                'dfds': ['dfds a/s'],
                'viscaria': ['gruvaktiebolaget viscaria'],
                'volvocar': ['volvo car'],
                'volvo': ['aktiebolaget volvo', 'volvo car'],
            }
            
            # Add mapped variations
            for key, values in abbrev_map.items():
                if key in normalized or key in no_hyphen or key in base:
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
                return {
                    'type': 'official',
                    'data': portfolio_matches[ticker]
                }
                
            # Check official positions
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