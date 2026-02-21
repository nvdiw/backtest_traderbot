# Backtest Trader Bot

BTC strategy backtesting bot in Python.  
It reads historical candle CSV data, simulates trades candle-by-candle, and outputs performance reports.

## Features
- Long/short backtesting with fee and liquidation handling
- Scoring-based entries/exits (EMA/MA, ADX, ATR, volume, momentum)
- Post-cross sharp-move negative exit score logic
- Monthly controls and loss-streak stop logic
- Parameter optimization with multiprocessing
- Interactive chart rendering for backtest review

## Project Structure
- `ma_strategy.py`: main strategy/backtest engine
- `optimize.py`: grid-search optimizer
- `trade_csv_logger.py`: trade log writer
- `trademanager.py`: position open/close/liquidation management
- `check_monthly_data.py`: monthly summary generator
- `chart_renderer.py`: chart UI
- `data_candle/`: historical input candles
- `outputs/`: generated files
  - `outputs/trades/data_orders.csv`
  - `outputs/monthly/monthly_data_orders.csv`
  - `outputs/optimize/optimization_results.csv`
  - `outputs/optimize/best_params.txt`

## Requirements
- Python 3.9+
- `pandas`
- `numpy`
- `mplfinance`

Install:
```bash
pip install pandas numpy mplfinance
```

## Required Candle CSV Columns
- `Open time`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`
- `Close time`

Default data path is configured in `ma_strategy.py`:
`./data_candle/btc_15m_data_2018_to_2025.csv`

## Run Backtest
1. Set date range in `ma_strategy.py`:
   - `start, end = get_candle_index(("YYYY-MM-DD", "YYYY-MM-DD"))`
2. Run:
```bash
python ma_strategy.py
```
3. Check outputs in `outputs/`.

## Run Optimization
1. Edit `param_grid` in `optimize.py`
2. Run:
```bash
python optimize.py -w 8
```
3. Review:
- `outputs/optimize/optimization_results.csv`
- `outputs/optimize/best_params.txt`

## Recent Strategy/Project Updates
- Added negative exit score component:
  - If a sharp move is detected in the lookback window (default `400` candles),
    and EMA/MA cross happened, a temporary post-cross penalty is applied for `15` candles.
- Sharp move detection improved to strongest directional move (ordered move), not simple high/low span.
- Added monthly loss-streak stop controls:
  - `consecutive_losses_month_stop_filter`
  - `consecutive_losses_stop_until_month`
- Output files reorganized under `outputs/` folders for cleaner repository structure.
- Optimizer and summary writers now create output directories automatically.

## Notes
- Optimization mode disables per-trade CSV logging for speed.
- If CSV is open in another app (like Excel), writing may wait/fail until file is closed.
- This repository is for research/education, not financial advice.

