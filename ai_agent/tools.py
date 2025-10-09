"""
AI Tools - Functions that the AI agent can call
Provides portfolio analysis, stock data, report downloads, and web search capabilities.
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
import subprocess
import re
from pathlib import Path


class AITools:
    """Collection of tools available to the AI agent."""
    
    # Class-level constant for downloads directory
    DOWNLOADS_DIR = Path('data/downloads')
    
    def __init__(self, portfolio=None):
        """
        Initialize tools with portfolio context.
        
        Args:
            portfolio: PortfolioManager instance
        """
        self.portfolio = portfolio
        
        # Ensure downloads directory exists
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Database of Swedish company investor relations pages
        self.company_ir_urls = {
            'VOLV-B': 'https://www.volvogroup.com/en/investors.html',
            'VOLCAR-B': 'https://www.volvocars.com/intl/v/car-safety/highlights',
            'ASSA-B': 'https://www.assaabloy.com/en/com/investors',
            'ERIC-B': 'https://www.ericsson.com/en/investors',
            'HM-B': 'https://hmgroup.com/investors/',
            'SAND': 'https://www.home.sandvik/en/investors/',
            'SKF-B': 'https://investors.skf.com/',
            'SSAB-B': 'https://www.ssab.com/en/investors',
            'BOL': 'https://www.boliden.com/investors',
            'ATCO-A': 'https://www.atlascopco.com/en/investors',
            'ATCO-B': 'https://www.atlascopco.com/en/investors',
            'SCA-B': 'https://www.sca.com/en/investors/',
            'ALLEI': 'https://www.alleima.com/en/investors/',
            'ALIV-SDB': 'https://www.alleima.com/en/investors/',
            'BILL': 'https://www.billerudkorsnas.com/investors',
            'AZN': 'https://www.astrazeneca.com/investors.html',
            'ELUX-B': 'https://www.electroluxgroup.com/en/investors/',
            'SAAB-B': 'https://investors.saab.com/',
            'SWED-A': 'https://www.swedbank.com/investors.html',
            'SHB-B': 'https://www.handelsbanken.com/en/investors',
            'SEB-A': 'https://sebgroup.com/investors',
            'TELIA': 'https://www.teliacompany.com/en/investors/',
            'KINV-B': 'https://www.kinnevik.com/en/investors/',
            'INVE-B': 'https://www.investorab.com/investors/',
            'NIBE-B': 'https://www.nibe.com/investors',
            'GETI-B': 'https://www.getinge.com/int/about-us/investors/',
            'HEXA-B': 'https://hexatronic.com/en/investors/',
            'EPI-B': 'https://www.epiroc.com/en/investors',
            'SINCH': 'https://www.sinch.com/investors/',
            'EVO': 'https://www.evolution.com/investors/',
        }
    
    def get_tool_definitions(self) -> List[Dict]:
        """
        Get tool definitions in Anthropic/OpenAI format.
        
        Returns:
            List of tool definition dictionaries
        """
        return [
            {
                "name": "get_portfolio_summary",
                "description": "Get a summary of the current stock portfolio including total value, number of stocks, and performance metrics.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "include_details": {
                            "type": "boolean",
                            "description": "Whether to include detailed stock-by-stock breakdown"
                        }
                    }
                }
            },
            {
                "name": "get_stock_info",
                "description": "Get detailed information about a specific stock in the portfolio including current price, holdings, and profit/loss.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'VOLV-B', 'ASSA-B')"
                        }
                    },
                    "required": ["ticker"]
                }
            },
            {
                "name": "calculate_portfolio_metrics",
                "description": "Calculate various portfolio metrics like diversification, sector exposure, risk metrics, etc.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "metrics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of metrics to calculate: 'diversification', 'concentration', 'sector_exposure', 'top_performers', 'worst_performers'"
                        }
                    }
                }
            },
            {
                "name": "search_company_info",
                "description": "Search for company information including latest news, financial reports, and announcements.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string",
                            "description": "Company name or ticker"
                        },
                        "info_type": {
                            "type": "string",
                            "description": "Type of information: 'news', 'reports', 'financials', 'all'"
                        }
                    },
                    "required": ["company_name"]
                }
            },
            {
                "name": "download_company_report",
                "description": "Automatically find and download a company's quarterly/interim or annual report from their investor relations page.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'ALLEI', 'VOLV-B')"
                        },
                        "report_type": {
                            "type": "string",
                            "description": "Type of report: 'interim', 'annual', 'quarterly' (default: 'interim')"
                        },
                        "quarter": {
                            "type": "string",
                            "description": "Quarter: 'Q1', 'Q2', 'Q3', 'Q4' (default: 'Q3')"
                        },
                        "year": {
                            "type": "string",
                            "description": "Year of report (default: '2024')"
                        }
                    },
                    "required": ["ticker"]
                }
            },
            {
                "name": "analyze_stock_correlation",
                "description": "Analyze correlation between stocks in the portfolio to understand diversification.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker1": {
                            "type": "string",
                            "description": "First stock ticker"
                        },
                        "ticker2": {
                            "type": "string",
                            "description": "Second stock ticker (optional, if not provided shows all correlations)"
                        }
                    }
                }
            },
            {
                "name": "search_web",
                "description": "Search the web for information about companies, financial reports, news, or general stock market information.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'Alleima Q2 2024 interim report', 'Volvo latest news')"
                        },
                        "result_count": {
                            "type": "integer",
                            "description": "Number of search results to return (1-5, default 3)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "download_file",
                "description": "Download a file from a URL (PDF reports, documents, etc.) and optionally open it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full URL of the file to download"
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional custom filename for the downloaded file"
                        },
                        "open_after": {
                            "type": "boolean",
                            "description": "Whether to open the file after downloading (default true)"
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "open_file",
                "description": "Open a file that exists on the system (useful for re-opening downloaded reports).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Filename or path to file (e.g., 'ALLEI_Q3_2024.pdf') - defaults to data/downloads/ folder"
                        }
                    },
                    "required": ["filepath"]
                }
            },
            {
                "name": "list_downloads",
                "description": "List files in the yspy downloads folder to see what reports are available to open.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "filter_ext": {
                            "type": "string",
                            "description": "Optional file extension to filter by (e.g., 'pdf')"
                        }
                    },
                    "required": []
                }
            }
        ]
    
    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Execute a tool by name with given input.
        
        Args:
            tool_name: Name of the tool to execute
            tool_input: Dictionary of input parameters
            
        Returns:
            String result of tool execution
        """
        tool_methods = {
            "get_portfolio_summary": self.get_portfolio_summary,
            "get_stock_info": self.get_stock_info,
            "calculate_portfolio_metrics": self.calculate_portfolio_metrics,
            "search_company_info": self.search_company_info,
            "download_company_report": self.download_company_report,
            "analyze_stock_correlation": self.analyze_stock_correlation,
            "search_web": self.search_web,
            "download_file": self.download_file,
            "open_file": self.open_file,
            "list_downloads": self.list_downloads,
        }
        
        method = tool_methods.get(tool_name)
        if not method:
            return f"Error: Unknown tool '{tool_name}'"
        
        try:
            return method(**tool_input)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    
    def get_portfolio_summary(self, include_details: bool = False) -> str:
        """Get portfolio summary."""
        if not self.portfolio:
            return "Portfolio not available."
        
        try:
            from ui.display_utils import calculate_portfolio_totals
            totals = calculate_portfolio_totals(self.portfolio)
            
            summary = f"""
Portfolio Summary:
-----------------
Total Value:     {totals['total_value']:.2f} SEK
Total Buy Value: {totals['buy_value']:.2f} SEK
Total Profit:    {totals['total_value'] - totals['buy_value']:.2f} SEK ({((totals['total_value'] - totals['buy_value']) / totals['buy_value'] * 100):.2f}%)
Number of Stocks: {len(self.portfolio.stocks)}
"""
            
            if include_details:
                summary += "\n\nStock Holdings:\n"
                for ticker, stock in self.portfolio.stocks.items():
                    try:
                        price_obj = stock.get_price_info()
                        current_price = price_obj.get_current_sek() if price_obj else 0
                        total_shares = sum(s.volume for s in stock.holdings)
                        total_value = total_shares * current_price if current_price else 0
                        summary += f"  {ticker}: {total_shares} shares @ {current_price:.2f} = {total_value:.2f} SEK\n"
                    except Exception:
                        pass
            
            return summary.strip()
        
        except Exception as e:
            return f"Error getting portfolio summary: {str(e)}"
    
    def get_stock_info(self, ticker: str) -> str:
        """Get detailed stock information."""
        if not self.portfolio:
            return "Portfolio not available."
        
        # Normalize ticker
        ticker_upper = ticker.upper().replace('.ST', '_ST')
        
        stock = self.portfolio.stocks.get(ticker_upper)
        if not stock:
            return f"Stock '{ticker}' not found in portfolio."
        
        try:
            price_obj = stock.get_price_info()
            current_price = price_obj.get_current_sek() if price_obj else 0
            
            total_shares = sum(s.volume for s in stock.holdings)
            total_cost = sum(s.volume * s.price for s in stock.holdings)
            avg_price = total_cost / total_shares if total_shares > 0 else 0
            current_value = total_shares * current_price if current_price else 0
            profit_loss = current_value - total_cost
            profit_pct = (profit_loss / total_cost * 100) if total_cost > 0 else 0
            
            info = f"""
Stock: {ticker_upper}
-------------------
Current Price:  {current_price:.2f} SEK
Total Shares:   {total_shares}
Average Cost:   {avg_price:.2f} SEK
Total Cost:     {total_cost:.2f} SEK
Current Value:  {current_value:.2f} SEK
Profit/Loss:    {profit_loss:.2f} SEK ({profit_pct:.2f}%)

Holdings:
"""
            for i, holding in enumerate(stock.holdings, 1):
                date_str = holding.date.strftime("%Y-%m-%d") if hasattr(holding.date, 'strftime') else str(holding.date)
                info += f"  {i}. {holding.volume} shares @ {holding.price:.2f} (bought {date_str})\n"
            
            return info.strip()
        
        except Exception as e:
            return f"Error getting stock info: {str(e)}"
    
    def calculate_portfolio_metrics(self, metrics: List[str] = None) -> str:
        """Calculate portfolio metrics."""
        if not self.portfolio:
            return "Portfolio not available."
        
        if not metrics:
            metrics = ['diversification', 'top_performers', 'worst_performers']
        
        result = "Portfolio Metrics:\n" + "=" * 50 + "\n\n"
        
        try:
            # Get all stock values
            stock_values = {}
            for ticker, stock in self.portfolio.stocks.items():
                try:
                    price_obj = stock.get_price_info()
                    current_price = price_obj.get_current_sek() if price_obj else 0
                    total_shares = sum(s.volume for s in stock.holdings)
                    total_cost = sum(s.volume * s.price for s in stock.holdings)
                    current_value = total_shares * current_price if current_price else 0
                    profit_pct = ((current_value - total_cost) / total_cost * 100) if total_cost > 0 else 0
                    
                    stock_values[ticker] = {
                        'value': current_value,
                        'cost': total_cost,
                        'profit_pct': profit_pct,
                        'shares': total_shares
                    }
                except Exception:
                    pass
            
            total_value = sum(s['value'] for s in stock_values.values())
            
            # Diversification / Concentration
            if 'diversification' in metrics or 'concentration' in metrics:
                result += "Portfolio Concentration:\n"
                sorted_stocks = sorted(stock_values.items(), key=lambda x: x[1]['value'], reverse=True)
                for ticker, data in sorted_stocks[:5]:
                    pct = (data['value'] / total_value * 100) if total_value > 0 else 0
                    result += f"  {ticker}: {pct:.1f}% ({data['value']:.0f} SEK)\n"
                result += "\n"
            
            # Top performers
            if 'top_performers' in metrics:
                result += "Top Performers (by return %):\n"
                sorted_by_return = sorted(stock_values.items(), key=lambda x: x[1]['profit_pct'], reverse=True)
                for ticker, data in sorted_by_return[:5]:
                    result += f"  {ticker}: {data['profit_pct']:+.2f}%\n"
                result += "\n"
            
            # Worst performers
            if 'worst_performers' in metrics:
                result += "Worst Performers (by return %):\n"
                sorted_by_return = sorted(stock_values.items(), key=lambda x: x[1]['profit_pct'])
                for ticker, data in sorted_by_return[:5]:
                    result += f"  {ticker}: {data['profit_pct']:+.2f}%\n"
                result += "\n"
            
            return result.strip()
        
        except Exception as e:
            return f"Error calculating metrics: {str(e)}"
    
    def search_company_info(self, company_name: str, info_type: str = "all") -> str:
        """Search for company information (placeholder - would need real implementation)."""
        # This would integrate with financial news APIs, company websites, etc.
        return f"""
Company Information Search for: {company_name}
Type: {info_type}

Note: This feature requires integration with financial news APIs.
Some options:
- Financial Modeling Prep API
- Alpha Vantage
- Yahoo Finance
- Company investor relations pages

To implement, you would need to:
1. Register for API keys
2. Make HTTP requests to fetch data
3. Parse and format results
"""
    
    def download_company_report(self, ticker: str, report_type: str = "interim", quarter: str = "Q3", year: str = "2024") -> str:
        """
        Download company report by searching common URL patterns.
        
        Args:
            ticker: Stock ticker
            report_type: Type of report (interim, annual, quarterly)
            quarter: Quarter (Q1, Q2, Q3, Q4)
            year: Year of report
            
        Returns:
            Status message with download info or instructions
        """
        ticker_upper = ticker.upper().replace('.ST', '_ST')
        
        # Get company name and IR URL
        ir_url = self.company_ir_urls.get(ticker_upper)
        
        if not ir_url:
            return f"""
No investor relations URL found for {ticker}.

Please provide the direct URL to the report PDF, and I can download it using:
download_file(url="https://company.com/report.pdf")
"""
        
        # Try to fetch the IR page and find PDF links
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            
            response = requests.get(ir_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Find all PDF links
            import re
            pdf_links = re.findall(r'href="([^"]*\.pdf)"', response.text, re.IGNORECASE)
            pdf_links += re.findall(r'href=\'([^\']*\.pdf)\'', response.text, re.IGNORECASE)
            
            # Filter for relevant reports (quarterly/interim reports)
            relevant_keywords = [
                quarter.lower(), year, 'interim', 'quarterly', 'delårsrapport', 
                'kvartalsrapport', 'q1', 'q2', 'q3', 'q4'
            ]
            
            relevant_pdfs = []
            for link in pdf_links:
                link_lower = link.lower()
                # Check if link contains relevant keywords
                if any(keyword in link_lower for keyword in relevant_keywords):
                    # Make absolute URL if relative
                    if link.startswith('/'):
                        from urllib.parse import urlparse
                        parsed = urlparse(ir_url)
                        link = f"{parsed.scheme}://{parsed.netloc}{link}"
                    elif not link.startswith('http'):
                        link = ir_url.rstrip('/') + '/' + link.lstrip('/')
                    relevant_pdfs.append(link)
            
            if relevant_pdfs:
                # Try to download the most relevant one (first match)
                best_match = relevant_pdfs[0]
                
                # Use download_file to actually download it
                result = self.download_file(best_match, filename=f"{ticker_upper}_{quarter}_{year}.pdf", open_after=True)
                return f"Found and downloaded report from {ir_url}\n\n{result}"
            else:
                # No PDF found, provide guidance
                result = f"""
Checked {ir_url} but couldn't find a direct link to {quarter} {year} {report_type} report.

PDF links found on page: {len(pdf_links)}

Next steps:
1. Visit {ir_url} directly
2. Look for "Reports" or "Financial Information" section  
3. Find the {quarter} {year} report
4. Copy the PDF URL and tell me: "Download this: [URL]"

Alternatively, try searching: "search_web {ticker} {quarter} {year} interim report PDF"
"""
                if pdf_links:
                    result += f"\n\nOther PDF links found:\n"
                    for link in pdf_links[:5]:  # Show first 5
                        result += f"  - {link}\n"
                
                return result
                
        except requests.exceptions.RequestException as e:
            return f"""
Could not access {ir_url}: {str(e)}

To download the report:
1. Visit {ir_url} manually
2. Find the {quarter} {year} {report_type} report
3. Copy the PDF URL
4. Tell me: "Download this: [URL]"

Or try: "search_web {ticker} {quarter} {year} report PDF"
"""
        except Exception as e:
            return f"Error searching for report: {str(e)}"
        # with open(filename, 'wb') as f:
        #     f.write(response.content)
        # 
        # if open_viewer:
        #     viewer = AI_CONFIG.get('pdf_viewer', 'xdg-open')
        #     subprocess.Popen([viewer, filename])
        #     result += f"\n✓ Opened in {viewer}"
        
        return result
    
    def analyze_stock_correlation(self, ticker1: str = None, ticker2: str = None) -> str:
        """Analyze stock correlation."""
        if not self.portfolio:
            return "Portfolio not available."
        
        try:
            # This would use the correlation analysis from your existing code
            from correlation_analysis import analyze_correlations
            
            # Get historical data for analysis
            # This is simplified - you'd need to integrate with your existing correlation code
            
            result = """
Stock Correlation Analysis:

Note: This requires historical price data analysis.
Your yspy app already has correlation analysis in correlation_analysis.py.

To get correlation data, you can:
1. Use the correlation analysis feature in the main menu
2. Ensure historical price data is up to date
3. The correlation matrix shows how stocks move together

High correlation (>0.7): Stocks move similarly (less diversification)
Low correlation (<0.3): Stocks move independently (better diversification)
Negative correlation (<0): Stocks move in opposite directions (hedge)
"""
            
            if ticker1 and ticker2:
                result += f"\nRequested correlation: {ticker1} vs {ticker2}"
            
            return result
        
        except Exception as e:
            return f"Error analyzing correlation: {str(e)}"
    
    def search_web(self, query: str, result_count: int = 3) -> str:
        """
        Search the web for information.
        
        Args:
            query: Search query
            result_count: Number of results to return (max 5)
            
        Returns:
            Search results as formatted text
        """
        try:
            # First, check if query mentions a ticker we have IR URLs for
            query_upper = query.upper()
            matched_ticker = None
            for ticker in self.company_ir_urls:
                if ticker in query_upper or ticker.replace('-', '') in query_upper:
                    matched_ticker = ticker
                    break
            
            result = f"Web Search: {query}\n" + "=" * 60 + "\n\n"
            
            # If we matched a ticker, provide the IR page
            if matched_ticker:
                ir_url = self.company_ir_urls[matched_ticker]
                company_name = self._get_company_name(matched_ticker)
                result += f"✓ Known Company Investor Relations Page:\n\n"
                result += f"Company: {company_name} ({matched_ticker})\n"
                result += f"Investor Relations: {ir_url}\n"
                result += f"\nCommon report sections on IR pages:\n"
                result += f"  • Financial Reports / Rapporter\n"
                result += f"  • Quarterly Reports / Delårsrapporter\n"
                result += f"  • Annual Reports / Årsredovisningar\n"
                result += f"  • Presentations / Presentationer\n\n"
                result += f"To download a report:\n"
                result += f"1. Visit: {ir_url}\n"
                result += f"2. Look for 'Financial Reports' or 'Rapporter'\n"
                result += f"3. Find the latest quarterly/annual report\n"
                result += f"4. Right-click the PDF link and copy the URL\n"
                result += f"5. Tell me: 'Download this: [URL]'\n\n"
                
                # Try to construct likely report URLs
                company_domain = ir_url.split('/')[2]
                result += f"Possible report URLs (try these):\n"
                result += f"  • https://{company_domain}/investors/reports/\n"
                result += f"  • https://{company_domain}/en/investors/financial-reports/\n"
                result += f"  • https://{company_domain}/investerare/rapporter/\n"
                
                return result
            
            # Try using requests + simple text search as fallback
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            
            # Try Google search (sometimes works without JS)
            google_url = f"https://www.google.com/search?q={encoded_query}"
            
            result += "Attempting web search...\n\n"
            result += f"Search Query: {query}\n\n"
            result += "Since automated web scraping can be unreliable, here are some tips:\n\n"
            result += "For Swedish Company Reports:\n"
            result += "1. Go to company's investor relations page\n"
            result += "2. Look for 'Financial Reports' or 'Rapporter'\n"
            result += "3. Latest reports are usually at the top\n"
            result += "4. Copy the PDF link and ask me to download it\n\n"
            
            result += "Common Swedish Company IR Pages:\n"
            for ticker, url in list(self.company_ir_urls.items())[:10]:
                company = self._get_company_name(ticker)
                result += f"  • {company}: {url}\n"
            
            result += f"\n... and {len(self.company_ir_urls) - 10} more in database\n\n"
            result += "Example: 'Download this: https://www.alleima.com/path/to/report.pdf'\n"
            
            return result
            
        except Exception as e:
            return f"Search error: {str(e)}\n\nPlease provide a direct URL to the report you want to download."
    
    def _get_company_name(self, ticker: str) -> str:
        """Get company name from ticker."""
        names = {
            'VOLV-B': 'Volvo Group',
            'VOLCAR-B': 'Volvo Cars',
            'ASSA-B': 'ASSA ABLOY',
            'ERIC-B': 'Ericsson',
            'HM-B': 'H&M',
            'SAND': 'Sandvik',
            'SKF-B': 'SKF',
            'SSAB-B': 'SSAB',
            'BOL': 'Boliden',
            'ATCO-A': 'Atlas Copco A',
            'ATCO-B': 'Atlas Copco B',
            'SCA-B': 'SCA',
            'ALLEI': 'Alleima',
            'ALIV-SDB': 'Alleima SDB',
            'BILL': 'Billerud',
            'AZN': 'AstraZeneca',
            'ELUX-B': 'Electrolux',
            'SAAB-B': 'SAAB',
            'SWED-A': 'Swedbank',
            'SHB-B': 'Handelsbanken',
            'SEB-A': 'SEB',
            'TELIA': 'Telia',
            'KINV-B': 'Kinnevik',
            'INVE-B': 'Investor',
            'NIBE-B': 'NIBE',
            'GETI-B': 'Getinge',
            'HEXA-B': 'Hexatronic',
            'EPI-B': 'Epiroc',
            'SINCH': 'Sinch',
            'EVO': 'Evolution',
        }
        return names.get(ticker, ticker)
    
    def download_file(self, url: str, filename: str = None, open_after: bool = True) -> str:
        """
        Download a file from URL.
        
        Args:
            url: URL to download from
            filename: Optional filename (auto-generated if not provided)
            open_after: Whether to open the file after download
            
        Returns:
            Status message
        """
        try:
            # Use the class-level downloads directory
            download_dir = self.DOWNLOADS_DIR
            download_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename if not provided
            if not filename:
                # Extract filename from URL
                filename = url.split('/')[-1].split('?')[0]
                if not filename or len(filename) < 3:
                    filename = f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            # Ensure .pdf extension for reports
            if not filename.endswith('.pdf') and 'pdf' in url.lower():
                filename += '.pdf'
            
            filepath = download_dir / filename
            
            # Download the file
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()
            
            # Save file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = filepath.stat().st_size / 1024  # KB
            
            result = f"""
✓ Download Complete!

File: {filename}
Size: {file_size:.1f} KB
Location: {filepath}
"""
            
            # Open the file if requested
            if open_after:
                try:
                    # Try different viewers
                    viewers = ['xdg-open', 'evince', 'okular', 'firefox']
                    for viewer in viewers:
                        try:
                            subprocess.Popen([viewer, str(filepath)], 
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                            result += f"\n✓ Opened with {viewer}"
                            break
                        except FileNotFoundError:
                            continue
                except Exception as e:
                    result += f"\n⚠ Could not auto-open file: {e}"
                    result += f"\nManually open: {filepath}"
            
            return result
            
        except requests.exceptions.RequestException as e:
            return f"Download failed: {str(e)}\n\nPlease check the URL and try again."
        except Exception as e:
            return f"Error downloading file: {str(e)}"

    def open_file(self, filepath: str) -> str:
        """
        Open a file on the system using the default application.
        SECURITY: Only allows opening files within data/downloads/ directory.
        
        Args:
            filepath: Filename or path (restricted to yspy downloads folder)
        
        Returns:
            Success or error message
        """
        try:
            # Define the allowed directory (project data/downloads)
            allowed_dir = self.DOWNLOADS_DIR.resolve()
            
            # Parse the user-provided path
            if filepath.startswith('/'):
                # Reject absolute paths outside allowed directory
                user_path = Path(filepath).resolve()
            elif filepath.startswith('~'):
                # Reject home directory paths
                user_path = Path(filepath).expanduser().resolve()
            else:
                # Relative path - resolve within allowed directory
                user_path = (allowed_dir / filepath).resolve()
            
            # SECURITY CHECK: Ensure the resolved path is within allowed directory
            try:
                user_path.relative_to(allowed_dir)
            except ValueError:
                return (
                    f"🔒 Security: Access denied to {filepath}\n\n"
                    f"For security reasons, you can only open files in:\n"
                    f"  {allowed_dir}\n\n"
                    f"Use list_downloads to see available files."
                )
            
            # Check if file exists
            if not user_path.exists():
                return f"❌ File not found: {user_path.name}\n\nTip: Use list_downloads to see available files."
            
            # Check if it's actually a file (not a directory)
            if not user_path.is_file():
                return f"❌ Not a file: {user_path.name}"
            
            # Try to open with default application
            import platform
            system = platform.system()
            
            if system == "Linux":
                # Try xdg-open first, then common PDF viewers and browsers
                viewers_to_try = [
                    'xdg-open',
                    'evince',
                    'okular', 
                    'atril',
                    'firefox',
                    'google-chrome',
                    'chromium-browser',
                    'xpdf',
                    'gv'
                ]
                
                for cmd in viewers_to_try:
                    try:
                        # Use Popen to start the process in the background
                        # This keeps the viewer running after the function returns
                        subprocess.Popen(
                            [cmd, str(user_path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True  # Detach from parent process
                        )
                        return f"✅ Opened file: {user_path.name}\n   Using: {cmd}"
                    except FileNotFoundError:
                        continue
                    except Exception:
                        continue
                
                # If nothing worked, return helpful message
                return (
                    f"⚠️  File exists but no PDF viewer found: {user_path.name}\n\n"
                    f"Install a PDF viewer:\n"
                    f"  • sudo apt install evince\n"
                    f"  • sudo apt install okular\n"
                    f"  • Or use: firefox {user_path}"
                )
            
            elif system == "Darwin":  # macOS
                subprocess.run(['open', str(user_path)], check=True)
                return f"✅ Opened file: {user_path.name}"
            
            elif system == "Windows":
                subprocess.run(['start', '', str(user_path)], shell=True, check=True)
                return f"✅ Opened file: {user_path.name}"
            
            else:
                return f"❌ Unsupported platform: {system}"
        
        except Exception as e:
            return f"❌ Error opening file: {str(e)}"

    def list_downloads(self, filter_ext: str = None) -> str:
        """
        List all files in the yspy downloads folder.
        
        Args:
            filter_ext: Optional file extension to filter by (e.g., 'pdf')
        
        Returns:
            Formatted list of files with details
        """
        try:
            download_dir = self.DOWNLOADS_DIR
            
            if not download_dir.exists():
                return f"📁 No downloads folder found yet.\n\nFiles will be saved to {download_dir}/ when you download them."
            
            # Get all files
            if filter_ext:
                files = list(download_dir.glob(f"*.{filter_ext}"))
            else:
                files = [f for f in download_dir.iterdir() if f.is_file()]
            
            if not files:
                ext_msg = f" with extension '.{filter_ext}'" if filter_ext else ""
                return f"📁 No files found{ext_msg} in {download_dir}/"
            
            # Sort by modification time (newest first)
            files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            result = f"📁 Downloaded Files ({len(files)} total):\n\n"
            
            for i, file in enumerate(files, 1):
                stat = file.stat()
                size_kb = stat.st_size / 1024
                mod_time = datetime.fromtimestamp(stat.st_mtime)
                time_str = mod_time.strftime("%Y-%m-%d %H:%M")
                
                result += f"{i}. {file.name}\n"
                result += f"   Size: {size_kb:.1f} KB | Modified: {time_str}\n"
            
            result += f"\n💡 To open a file: use open_file with the filename (e.g., 'open_file(\"{files[0].name}\")')"
            
            return result
            
        except Exception as e:
            return f"❌ Error listing downloads: {str(e)}"


if __name__ == "__main__":
    # Test tools
    tools = AITools()
    print("Tool Definitions:")
    print(json.dumps(tools.get_tool_definitions(), indent=2))
