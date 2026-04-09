import pandas as pd
import numpy as np
import os

# My Codes :
from trade_csv_logger import TradeCSVLogger
from indicators import Indicator
from get_candle_index import get_candle_index, get_month_start_indices
from trademanager import TradeManager
from check_monthly_data import write_monthly_summary
from chart_renderer import render_backtest_chart

start, end = get_candle_index(("2023-01-01","2024-02-23"))

# Fetch data from CSV file
def fetch_all_data(start: int, end: int):
    """Load only the required candle window from CSV (start:end)."""
    if start is None or end is None or end <= start:
        return None

    rows_to_read = end - start
    data = pd.read_csv(
        './data_candle/btc_15m_data_2018_to_2026.csv',
        skiprows=range(1, start + 1),
        nrows=rows_to_read,
        usecols=['Open time', 'Close time', 'Open', 'Close', 'Low', 'High', 'Volume'],
    )

    return {
        "Open time": data['Open time'].tolist(),
        "Close time": data['Close time'].tolist(),
        "Open": data['Open'].to_numpy(dtype=float),
        "Close": data['Close'].to_numpy(dtype=float),
        "Low": data['Low'].to_numpy(dtype=float),
        "High": data['High'].to_numpy(dtype=float),
        "Volume": data['Volume'].to_numpy(dtype=float)
    }

all_data = fetch_all_data(start, end)
open_prices = all_data["Open"]
close_prices = all_data["Close"]
open_times = all_data["Open time"]
close_times = all_data["Close time"]
low_prices = all_data["Low"]
high_prices = all_data["High"]
volume_prices = all_data["Volume"]

# normalize close_times by adding 0.001 seconds (1 ms) to make rounding consistent
close_times = (
    pd.to_datetime(close_times, utc=True) + pd.Timedelta(milliseconds=1)
).strftime("%Y-%m-%d %H:%M:%S.%f").tolist()

# --- performance: ensure numeric arrays and precompute rolling means (O(n)) ---
open_prices = np.asarray(open_prices, dtype=float)
close_prices = np.asarray(close_prices, dtype=float)
low_prices = np.asarray(low_prices, dtype=float)
high_prices = np.asarray(high_prices, dtype=float)
volume_prices = np.asarray(volume_prices, dtype=float)

