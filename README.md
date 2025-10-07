# yspy

A terminal-based stock portfolio management application featuring real-time price monitoring, comprehensive historical data analysis, and an intuitive ncurses interface.

![Status](https://img.shields.io/badge/status-alpha-orange)
![Python](https://img.shields.io/badge/python-3.7+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![GitHub](https://img.shields.io/badge/GitHub-H4jen%2Fyspy-blue?logo=github)](https://github.com/H4jen/yspy)

## 📺 Watch Screen Demo

![Watch Screen](watchscreen.PNG)

*Real-time portfolio monitoring with live price updates, historical data, and color-coded performance indicators*

> ⚠️ **Alpha Release**: This project is in active development. Features and APIs may change. Use at your own risk and always backup your portfolio data.

---

## 🚀 Quick Installation

### For Impatient Users (3 commands)

```bash
git clone https://github.com/H4jen/yspy.git
cd yspy
pip install -r requirements.txt
./yspy.py
```

### Recommended Installation (with virtual environment)

```bash
# 1. Clone the repository
git clone https://github.com/H4jen/yspy.git
cd yspy

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Linux/macOS
# venv\Scripts\activate   # On Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run yspy
./yspy.py
```

**Windows Users**: Install `windows-curses` with `pip install windows-curses`

---

## 📘 Understanding the Basics

### What Are Stocks, Shares, and Tickers?

**Stocks** represent ownership in a company. When you buy stock, you become a partial owner of that business.

**Shares** are the individual units of stock. If you buy 100 shares of Apple, you own 100 units of Apple stock.

**Ticker Symbols** (or just "tickers") are unique abbreviations used to identify publicly traded companies:
- `AAPL` = Apple Inc.
- `MSFT` = Microsoft Corporation
- `VOLV-B.ST` = Volvo B shares on Stockholm Stock Exchange

Different stock exchanges use different ticker formats:
- **US stocks**: Simple letters (e.g., `TSLA`, `GOOGL`)
- **European stocks**: Often include exchange suffix (e.g., `.ST` for Stockholm, `.L` for London)

### Data Source: Yahoo Finance

This application relies on **Yahoo Finance** as its data provider, accessed through the **yfinance** Python library.

**What is Yahoo Finance?**
- One of the world's largest free financial data providers
- Offers real-time and historical stock prices
- Covers global stock exchanges
- Provides company information, financial data, and market statistics

**Why yfinance?**
- ✅ **Free to use** - No API keys or subscriptions required
- ✅ **Global coverage** - Access to stocks from major exchanges worldwide
- ✅ **Comprehensive data** - Real-time prices, historical data, company info
- ✅ **Well-maintained** - Active community and regular updates
- ✅ **Easy to use** - Simple Python interface

**Important Limitations:**
- ⚠️ **Not official** - yfinance uses Yahoo Finance's public interface (not an official API)
- ⚠️ **No guarantees** - Yahoo can change their system at any time
- ⚠️ **Rate limiting** - Too many requests may result in temporary blocks
- ⚠️ **Data accuracy** - While generally reliable, always verify critical financial decisions
- ⚠️ **Delayed data** - Some exchanges may have 15-20 minute delays for free data

**For Production/Commercial Use:**
If you need guaranteed uptime and data accuracy, consider paid alternatives:
- Alpha Vantage
- IEX Cloud
- Polygon.io
- Official exchange APIs

This application is designed for **personal portfolio tracking and educational purposes**.

## ✨ Features

### Core Functionality
- 📈 **Real-time Stock Monitoring** - Live price updates with configurable auto-refresh intervals
- 💼 **Portfolio Management** - Complete transaction tracking with buy/sell operations
- 📊 **Historical Analysis** - Multi-timeframe data (1 day to 1 year) with percentage changes
- 🔗 **Correlation Analysis** - Statistical analysis and visualization of stock relationships
- 💱 **Multi-Currency Support** - Automatic conversion with live exchange rates (SEK default)

### Advanced Capabilities
- 🔄 **Automated Background Updates** - Continuous historical data refresh without blocking UI
- ✅ **Individual Ticker Validation** - Isolated error handling prevents cascade failures
- 🛡️ **Data Quality Assurance** - Automatic detection and correction of data anomalies
- 🔁 **Intelligent Fallback System** - Preserves working data when APIs fail
- ⚡ **Performance Optimized** - Thread-safe operations with efficient caching

### User Experience
- 🖥️ **Full-screen Terminal UI** - Professional ncurses interface with scrolling support
- 🎨 **Color-Coded Display** - Intuitive green/red indicators for price movements
- 👁️ **Multiple View Modes** - Toggle between portfolio overview and detailed holdings
- 🚀 **Non-blocking Operations** - Smooth, responsive interface during data updates

## 🚀 Quick Start

> **⚠️ Alpha Software Notice**: This application is under active development. While functional, it may contain bugs and undergo significant changes. Please backup your portfolio data regularly.

### Prerequisites
- Python 3.7 or higher
- Terminal with color support
- Internet connection for API access

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/H4jen/yspy.git
cd yspy
```

**2. Set up virtual environment (recommended)**
```bash
python3 -m venv venv
source venv/bin/activate  # On Linux/macOS
# venv\Scripts\activate   # On Windows
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

> **Note for Windows users**: You'll need to install `windows-curses`:
> ```bash
> pip install windows-curses
> ```

**4. Launch the application**
```bash
python3 yspy.py
```

### Quick Install (Without Virtual Environment)
```bash
pip install -r requirements.txt
python3 yspy.py
```

## 📖 Usage

### Main Menu Commands
| Command | Function | Description |
|---------|----------|-------------|
| `1` | List Stocks | View all stocks in your portfolio |
| `2` | Add Stock | Add a new stock by ticker symbol |
| `3` | Remove Stock | Remove a stock from portfolio |
| `4` | List Shares | View detailed share holdings and transactions |
| `5` | Buy Shares | Purchase shares with automatic price tracking |
| `6` | Sell Shares | Sell shares with profit/loss calculation |
| `7` | Watch Stocks | Real-time monitoring mode (10-second refresh) |
| `8` | Profit per Stock | Individual stock performance analysis |
| `9` | All Profits | Portfolio-wide profit summary |
| `c` | Correlation Analysis | Statistical analysis and visualization |
| `q` | Quit | Exit the application |

### Watch Mode Features
- **Live Updates**: Automatic price refresh every 10 seconds
- **Price History**: 6-dot color-coded change indicator
- **Multi-Timeframe**: 1d, 2d, 3d, 1w, 2w, 1m, 3m, 6m, 1y percentage changes
- **View Toggle**: Switch between portfolio overview and detailed shares view
- **Color Coding**: Green for gains, red for losses
- **Portfolio Stats**: Total value, overall performance, and market status

## 🏗️ Architecture

### Project Structure

```
yspy/
├── 📱 Core Application
│   ├── yspy.py               # Application entry point (main executable)
│   ├── yspy_app.py           # Main application logic
│   ├── app_config.py               # Configuration management
│   └── portfolio_manager.py        # Portfolio management engine
│
├── 🎨 User Interface
│   └── ui/
│       ├── display_utils.py        # Display utilities and formatting
│       ├── stock_display.py        # Stock visualization components
│       └── profit_utils.py         # Profit display calculations
│
├── 📊 Features
│   ├── menu_handlers.py            # Command handlers
│   ├── ui_handlers.py              # UI event handlers
│   └── correlation_analysis.py     # Statistical analysis tools
│
├── 💾 Data
│   ├── portfolio/                  # User portfolio data (gitignored)
│   ├── data/                       # Application data
│   └── requirements.txt            # Python dependencies
│
└── 📚 Documentation
    ├── README.md                   # This file
    └── docs/                       # Detailed documentation
```

### Design Principles

**Separation of Concerns**
- Each module has a single, well-defined responsibility
- Clear boundaries between UI, business logic, and data layers
- Easy to test, maintain, and extend

**Reliability & Robustness**
- Comprehensive error handling at every level
- Graceful degradation when APIs fail
- Automatic data validation and correction
- Transaction-safe data operations

**Performance & Scalability**
- Background threading for non-blocking operations
- Intelligent caching minimizes API calls
- Efficient data structures for fast access
- Memory-optimized historical data storage

## 🔧 Technical Stack

### Core Technologies
| Technology | Purpose | Version |
|------------|---------|---------|
| **Python** | Core language | 3.7+ |
| **ncurses** | Terminal UI | Built-in |
| **yfinance** | Market data API | 0.2.28+ |
| **pandas** | Data manipulation | 2.0.0+ |
| **numpy** | Numerical operations | 1.24.0+ |
| **matplotlib** | Data visualization | 3.7.0+ |
| **requests** | HTTP client | 2.31.0+ |

All dependencies are specified in `requirements.txt`.

### Data Sources
- **Stock Market Data**: [Yahoo Finance](https://finance.yahoo.com/) via the [yfinance library](https://github.com/ranaroussi/yfinance)
  - Real-time stock prices (with possible 15-20 min delay)
  - Historical price data (daily, weekly, monthly)
  - Company information and market statistics
  - **Note**: Unofficial API - subject to Yahoo's terms and availability
- **Currency Exchange Rates**: Multiple currency conversion APIs with automatic fallback
- **Historical Data**: Local CSV cache with automatic updates and validation

**Data Disclaimer**: This application uses publicly available data from Yahoo Finance for personal portfolio tracking. The data is provided "as-is" and should not be the sole basis for investment decisions. Always consult with financial professionals and verify data from official sources before making investment choices.

##  Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Architecture Overview](docs/REFACTORING_COMPLETE.md)** - System design and structure
- **[Feature Implementations](docs/1Y_DATA_IMPLEMENTATION.md)** - Detailed feature guides
- **[Historical Data System](docs/HISTORICAL_MARKET_DATA.md)** - Data management deep dive
- **[Capital Tracking](docs/CAPITAL_TRACKING_IMPLEMENTATION.md)** - Investment tracking guide
- **[TWR Implementation](docs/TRUE_TWR_IMPLEMENTATION.md)** - Time-weighted returns

## 🧪 Development

### Running Tests
Tests are located in the `tests/` directory (gitignored):

```bash
# Run specific test suites
python3 tests/test_refactored_portfolio.py
python3 tests/test_watch_compatibility.py
python3 tests/test_1y_data.py
```

### Project Scripts
Utility scripts are in the `scripts/` directory (gitignored):

- Data import and export utilities
- Historical data management
- Portfolio maintenance tools

### Contributing
Contributions are welcome! Please ensure:

1. ✅ **Code Quality** - Follow existing code style and patterns
2. 📝 **Documentation** - Update relevant docs for new features
3. 🧪 **Testing** - Add tests for new functionality
4. 🏗️ **Architecture** - Maintain separation of concerns
5. ⚡ **Performance** - Consider background processing for data operations

## 🎯 Key Features Explained

### Real-Time Watch Mode
Experience live portfolio monitoring with:
- ⚡ **10-second refresh cycle** for up-to-the-minute data
- 📊 **6-dot price history** with color-coded indicators
- 📈 **Multi-timeframe analysis** from 1 day to 1 year
- 🎨 **Dynamic color coding** - Green for gains, red for losses
- 📱 **Responsive design** that adapts to terminal size
- 💼 **Portfolio totals** with real-time value tracking

### Automated Historical Data Management
Intelligent data handling includes:
- 🔄 **Background refresh** every 5 minutes without blocking UI
- ✅ **Data validation** automatically detects and corrects issues
- 🛡️ **Smart fallback** reconstructs missing data from hourly intervals
- 📦 **Efficient caching** minimizes API calls and load times
- 🔍 **Individual ticker processing** isolates errors to prevent cascade failures
- ⏰ **Staleness detection** automatically updates outdated data

### Profit & Loss Tracking
Comprehensive financial tracking:
- 💰 **Realized profits** from completed sell transactions
- 📊 **Unrealized gains** based on current market values
- 📈 **Per-stock analysis** with detailed breakdown by position
- 💼 **Portfolio summary** showing overall performance
- 📝 **Transaction history** with complete audit trail
- 🎯 **Cost basis tracking** using FIFO methodology

### Correlation Analysis
Advanced statistical tools:
- 📊 **Correlation matrices** between portfolio stocks
- 📈 **Visual plotting** with matplotlib integration
- 🔍 **Statistical significance** testing and metrics
- 🎨 **Interactive visualization** options
- 📉 **Historical comparisons** across different timeframes

## 🆘 Troubleshooting

### Common Issues and Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| **N/A values in display** | Background updates in progress | Wait 10-30 seconds for automatic resolution |
| **Slow startup** | Initial historical data load | Normal behavior; data cached for future use |
| **Missing historical data** | API unavailable or rate limit | Automatic fallback systems preserve existing data |
| **Price not updating** | Network connectivity issue | Check internet connection; app will retry automatically |
| **Curses errors on Windows** | Missing windows-curses package | Run `pip install windows-curses` |

### Debugging

**Check Application Logs**
```bash
tail -f yspy.log
```

**Verify Dependencies**
```bash
pip list | grep -E 'yfinance|pandas|numpy|matplotlib|requests'
```

**Test Network Connectivity**
```bash
python3 -c "import yfinance as yf; print(yf.Ticker('AAPL').info['currentPrice'])"
```

### Getting Help
1. 📋 Review `yspy.log` for detailed error messages
2. 🔍 Check the [documentation](docs/) for feature-specific guides
3. 🐛 Report issues on the GitHub repository with log excerpts
4. 💡 Check that your ticker symbols are valid (e.g., `AAPL` for Apple)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### What This Means
- ✅ Free to use for personal and commercial purposes
- ✅ Modify and distribute as you wish
- ✅ Private use allowed
- ⚠️ Provided "as is" without warranty
- 📝 Must include original license and copyright notice

### Alpha Status Disclaimer
This software is in **alpha stage**. While it's functional and actively used, it may:
- Contain bugs or unexpected behavior
- Have incomplete features or documentation
- Undergo breaking changes in future versions
- Require manual data migration between updates

**Recommendation**: Regular backups of your `portfolio/` directory are strongly advised.

## 🙏 Acknowledgments

- **[yfinance](https://github.com/ranaroussi/yfinance)** - Yahoo Finance API wrapper
- **[pandas](https://pandas.pydata.org/)** - Data analysis library
- **Python ncurses** - Terminal UI framework

---

<div align="center">

**Status: 🚧 Alpha Development**

Functional but under active development • Test coverage in progress • Breaking changes possible  
Real-time monitoring with 1-year historical data • Active feature development

Made with ❤️ for investors and developers

[Report Bug](https://github.com/H4jen/yspy/issues) · [Request Feature](https://github.com/H4jen/yspy/issues) · [Documentation](docs/)

</div>
