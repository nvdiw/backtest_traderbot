Trading Strategy Backtesting Engine (Python)

Description:
A professional Python-based backtesting engine designed to simulate and evaluate
trading strategies on historical market data under realistic market conditions.

This project focuses on clean architecture, modular strategy design, and real-world
trading constraints such as fees, leverage, liquidation, cooldown periods, and
monthly risk control.

NOTE:
Strategy executes ONLY on candle OPEN prices to avoid look-ahead bias.

--------------------------------------------------
Features:
- Historical OHLCV data backtesting (CSV-based)
- EMA & MA trend detection (EMA14 / MA50 / MA130 / MA200)
- Cross-based trade activation (one trade per cross)
- Entry & exit scoring system
- ATR-based dynamic exits
- ADX and volume filters
- Long and short position simulation
- Leverage and liquidation handling
- Monthly profit cap with auto stop trading
- Cooldown after large PnL events
- Fee-aware balance tracking
- Maximum drawdown and equity curve tracking
- Trade logging to CSV
- Monthly performance summary generation

--------------------------------------------------
Strategy Overview:

Entry Logic:
Trades are triggered only after an EMA14 / MA50 cross and confirmed using a
multi-factor scoring system including:
- Trend direction alignment
- Moving average distance
- Candle momentum
- ADX strength filter
- Volume and strong candle confirmation

A trade is opened only if the entry score reaches the defined threshold.

Exit Logic:
Exits are handled using a point-based scoring system combining:
- EMA slope weakness
- EMA / MA50 cross reversal
- Long-term trend degradation
- ATR-based adverse move detection
- ATR-based dynamic time-based exit

--------------------------------------------------
Project Structure:

data_candle/
  btc_15m_data_2018_to_2025.csv

indicators.py
trademanager.py
trade_csv_logger.py
get_candle_index.py
check_monthly_data.py
backtest.py

data_orders.csv
monthly_data_orders.csv

--------------------------------------------------
Requirements:
- Python 3.9 or higher
- Required libraries:
  - pandas
  - numpy

Install dependencies using:
pip install pandas numpy

--------------------------------------------------
How to Run:

1. Prepare market data:
   Place historical OHLCV CSV data inside:
   data_candle/btc_15m_data_2018_to_2025.csv

   Required columns:
   Open time, Close time, Open, High, Low, Close, Volume

2. Set backtest date range:
   Edit the following line in backtest.py:

   start, end = get_candle_index(("2025-01-01", "2025-12-18"))

3. Run the backtest:
   Open terminal in project directory and run:

   python main.py

--------------------------------------------------
Outputs:

Terminal Output:
- Total trades
- Win / loss statistics
- Final balance (with and without fees)
- Total profit percentage
- Maximum drawdown
- Win rate
- Backtest duration

Generated Files:
- data_orders.csv          (full trade log)
- monthly_data_orders.csv  (monthly performance summary)

--------------------------------------------------
Customization:
Main strategy parameters can be adjusted inside ma_strategy():

- trade_amount_percent
- leverage
- monthly_profit_percent_stop_trade
- adx_filter
- volume_filter
- entry_score_threshold
- exit_score_threshold
- cooldown_after_big_pnl

A tuning dictionary can also be passed programmatically for optimization.

--------------------------------------------------
Disclaimer:
This project is for research and educational purposes only.
It is NOT financial advice.
Past performance does NOT guarantee future results.
Use at your own risk.

--------------------------------------------------
Author:
Navid
Python Developer | Algorithmic Trading & Data Analysis
