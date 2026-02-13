# Backtest Trader Bot (English)

This project is a BTC strategy backtesting bot in Python.
It reads historical candles from CSV, runs the strategy candle-by-candle, and reports trading performance.

Important: entries and exits are evaluated on candle data (Open/High/Low/Close), and trade logs are saved to CSV.

## 1) What This Project Does
- Runs a backtest for long/short trades on historical BTC data.
- Uses EMA/MA trend logic with scoring rules, ADX/ATR/volume filters, leverage, liquidation checks, fees, and monthly controls.
- Saves detailed trade logs and monthly summaries.
- Supports parameter optimization with multiprocessing.

## 2) Project Files You Will Use Most
- `ma_strategy.py`: main backtest script.
- `optimize.py`: grid-search optimizer for strategy parameters.
- `data_candle/btc_15m_data_2018_to_2025.csv`: default data file used by the strategy.
- `data_orders.csv`: generated trade-by-trade results.
- `monthly_data_orders.csv`: generated monthly performance summary.
- `optimization_results.csv`: generated optimization output.
- `best_params.txt`: generated best optimization result.

## 3) Requirements
- Python 3.9+
- Packages:
  - `pandas`
  - `numpy`
  - `matplotlib`

Install:
```bash
pip install pandas numpy matplotlib
```

## 4) CSV Data Format (Required)
Default file path in code:
- `./data_candle/btc_15m_data_2018_to_2025.csv`

Required columns (exact names):
- `Open time`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`
- `Close time`

If your file name/path is different, update it in:
- `ma_strategy.py` (inside `fetch_all_data`)
- `get_candle_index.py` (global CSV load)

## 5) Run a Backtest (Step-by-Step)
1. Put your candle CSV in `data_candle/`.
2. Open `ma_strategy.py` and set the backtest range here:
   - `start, end = get_candle_index(("YYYY-MM-DD", "YYYY-MM-DD"))`
3. Run:
```bash
python ma_strategy.py
```
4. Check outputs:
   - terminal summary (wins/losses, balance, drawdown, win rate, etc.)
   - `data_orders.csv`
   - `monthly_data_orders.csv`

## 6) Run Optimization
1. Open `optimize.py`.
2. Edit `param_grid` to test the parameters you want.
3. Run (example with 8 workers):
```bash
python optimize.py -w 8
```
4. Outputs:
   - `optimization_results.csv`
   - `best_params.txt`

Notes:
- During optimization, per-trade CSV logging is disabled for speed.
- If `optimization_results.csv` is open in Excel, close it first (the script waits for file access).

## 7) Main Parameters You Can Tune
In `ma_strategy.py` (or via `tune` in optimization), common parameters include:
- `trade_amount_percent`
- `leverage`
- `monthly_profit_percent_stop_trade`
- `monthly_close_filter`
- `adx_filter`
- `volume_filter`
- `entry_score_threshold`
- `exit_score_threshold`
- `cooldown_after_big_pnl`
- `ema_16`, `ma_50`, `ma_100`, `ma_200`

## 8) Troubleshooting
- `FileNotFoundError`: check CSV path and file name.
- No trades opened: date range may be too short or filters too strict.
- CSV write permission errors: close `data_orders.csv` / `optimization_results.csv` in other apps.
- Slow optimization: reduce `param_grid` size or worker count.

## 9) Disclaimer
This repository is for research/education only.
It is not financial advice and not a live-trading system.


============================================================


# بک‌تست تریدر بات (فارسی)

این پروژه یک ربات بک‌تست استراتژی معاملاتی بیت‌کوین با پایتون است.
داده‌ی کندل را از فایل CSV می‌خواند، استراتژی را کندل‌به‌کندل اجرا می‌کند و خروجی عملکرد می‌دهد.

نکته مهم: ورود و خروج معاملات با داده‌های کندل (Open/High/Low/Close) ارزیابی می‌شود و لاگ معاملات در CSV ذخیره می‌شود.

## 1) این پروژه چه کاری انجام می‌دهد
- بک‌تست معاملات لانگ و شورت روی داده تاریخی BTC.
- استفاده از منطق EMA/MA با سیستم امتیازدهی، فیلتر ADX/ATR/Volume، اهرم، لیکوییدیشن، کارمزد و کنترل ماهانه.
- ذخیره لاگ کامل معاملات و گزارش ماهانه.
- پشتیبانی از بهینه‌سازی پارامترها با multiprocessing.

## 2) فایل‌های مهم پروژه
- `ma_strategy.py`: اسکریپت اصلی بک‌تست.
- `optimize.py`: اسکریپت بهینه‌سازی پارامترها.
- `data_candle/btc_15m_data_2018_to_2025.csv`: فایل دیتای پیش‌فرض.
- `data_orders.csv`: خروجی لاگ تک‌تک معاملات.
- `monthly_data_orders.csv`: خروجی خلاصه عملکرد ماهانه.
- `optimization_results.csv`: خروجی همه نتایج بهینه‌سازی.
- `best_params.txt`: بهترین نتیجه بهینه‌سازی.

## 3) پیش‌نیازها
- Python 3.9 یا بالاتر
- پکیج‌ها:
  - `pandas`
  - `numpy`
  - `matplotlib`

نصب:
```bash
pip install pandas numpy matplotlib
```

## 4) فرمت CSV موردنیاز
مسیر پیش‌فرض فایل دیتا در کد:
- `./data_candle/btc_15m_data_2018_to_2025.csv`

ستون‌های لازم (با همین نام دقیق):
- `Open time`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`
- `Close time`

اگر نام یا مسیر فایل دیتای شما فرق دارد، باید در این فایل‌ها اصلاح کنید:
- `ma_strategy.py` (داخل تابع `fetch_all_data`)
- `get_candle_index.py` (بارگذاری سراسری CSV)

## 5) اجرای بک‌تست (مرحله‌به‌مرحله)
1. فایل کندل خودت را داخل `data_candle/` قرار بده.
2. فایل `ma_strategy.py` را باز کن و این خط را برای بازه زمانی تنظیم کن:
   - `start, end = get_candle_index(("YYYY-MM-DD", "YYYY-MM-DD"))`
3. اجرا:
```bash
python ma_strategy.py
```
4. خروجی‌ها:
   - خلاصه در ترمینال (برد/باخت، موجودی نهایی، دراداون، وین‌ریت و...)
   - `data_orders.csv`
   - `monthly_data_orders.csv`

## 6) اجرای بهینه‌سازی
1. فایل `optimize.py` را باز کن.
2. `param_grid` را با پارامترهای موردنظر خودت تنظیم کن.
3. اجرا (مثال با 8 هسته):
```bash
python optimize.py -w 8
```
4. خروجی‌ها:
   - `optimization_results.csv`
   - `best_params.txt`

نکته‌ها:
- در حالت بهینه‌سازی، لاگ تک‌معامله‌ای CSV برای افزایش سرعت غیرفعال می‌شود.
- اگر `optimization_results.csv` در Excel باز باشد، اول ببندش (اسکریپت منتظر آزاد شدن فایل می‌ماند).

## 7) پارامترهای اصلی قابل تنظیم
در `ma_strategy.py` (یا با `tune` در بهینه‌سازی)، پارامترهای مهم:
- `trade_amount_percent`
- `leverage`
- `monthly_profit_percent_stop_trade`
- `monthly_close_filter`
- `adx_filter`
- `volume_filter`
- `entry_score_threshold`
- `exit_score_threshold`
- `cooldown_after_big_pnl`
- `ema_16`, `ma_50`, `ma_100`, `ma_200`

## 8) رفع خطاهای رایج
- `FileNotFoundError`: مسیر یا نام فایل CSV را چک کن.
- باز نشدن معامله: بازه زمانی کوتاه است یا فیلترها بیش از حد سخت هستند.
- خطای دسترسی فایل CSV: فایل‌های `data_orders.csv` یا `optimization_results.csv` را در برنامه‌های دیگر ببند.
- کند بودن بهینه‌سازی: اندازه `param_grid` یا تعداد worker را کمتر کن.

## 9) هشدار
این پروژه فقط برای تحقیق و آموزش است.
سیگنال مالی نیست و سیستم ترید زنده هم نیست.
