# NOTE: Strategy executes With candle Open prices, High prices, Low prices, Close prices

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


# start = get_candle_index("2025-01-01")   ----> 244944
# end = get_candle_index("2025-12-18")     ----> 278640

# get (index or ID) of start, end of csv
start, end = get_candle_index(("2023-01-01","2026-02-14"))
lst_month_starts = get_month_start_indices(start, end, just_index= True)

current_position = None  # None | "long" | "short"

# Fetch data from CSV file
def fetch_all_data(start: int, end: int):
    """Load only the required candle window from CSV (start:end)."""
    if start is None or end is None or end <= start:
        return None

    rows_to_read = end - start
    data = pd.read_csv(
        './data_candle/btc_15m_data_2018_to_2025.csv',
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

_INDICATOR_CACHE = {
    "ema": {},
    "ma": {},
    "adx": {},
    "atr": {},
    "atr_ma": {},
    "vol_avg": {},
}


def _cached_indicator(kind, key, builder):
    cache = _INDICATOR_CACHE[kind]
    if key not in cache:
        cache[key] = builder()
    return cache[key]


# Calculate Trade Duration
def trade_duration(open_time: str, close_time: str):
    # format: YYYY-MM-DD HH:MM:SS.microseconds

    def parse(t):
        t = t.strip()
        date, time = t.split(" ")
        y, m, d = map(int, date.split("-"))
        h, mi, s = time.split(":")
        s = int(float(s))  # drop microseconds
        return y, m, d, int(h), int(mi), s

    def to_seconds(y, m, d, h, mi, s):
        # days per month (no leap year handling for simplicity)
        mdays = [31,28,31,30,31,30,31,31,30,31,30,31]

        days = y * 365 + sum(mdays[:m-1]) + (d - 1)
        return days * 86400 + h * 3600 + mi * 60 + s

    o = to_seconds(*parse(open_time))
    c = to_seconds(*parse(close_time))

    diff = c - o

    days = diff // 86400
    diff %= 86400
    hours = diff // 3600
    diff %= 3600
    minutes = diff // 60

    return days, hours, minutes


# Main Trading Logic
def ma_strategy(tune: dict = None):

    global current_position

    # detect optimization mode early so we can disable I/O and heavy bookkeeping
    optimize = bool(tune.get('optimize')) if tune else False
    verbose = not optimize
    csv_logger = TradeCSVLogger(optimize=optimize)

    # ---- settings ----
    # Capital & position sizing
    balance = 1000                  # base balance
    leverage = 10                   # default leverage
    trade_amount_percent = 0.5      # 50% of balance per trade
    save_money = 0

    # Safe leverage levels
    safe_leverage_low = 2
    safe_leverage_med = 3
    safe_leverage_high = 4

    # Safe leverage activation thresholds (% of tactical balance)
    safe_leverage_balance_pct_low = 80
    safe_leverage_balance_pct_med = 80
    safe_leverage_balance_pct_high = 90
    # Save-money recovery (recover amount = 100 - trigger)
    save_money_recover_trigger_pct = 75

    # Monthly control
    monthly_profit_percent_stop_trade = 8  # stop trading month after reaching this profit %
    monthly_loss_percent_stop_trade = 19   # stop trading month after reaching this loss %
    monthly_compound = 3                   # raise tactical balance by this % for next month
    monthly_profit_close_filter = True
    monthly_loss_close_filter = False

    # Filters & behavior switches
    adx_filter = True
    volume_filter = True
    atr_filter = True
    consecutive_losses_month_stop_filter = False
    skip_logic = False

    # Cooldown
    cooldown_after_big_pnl = 4 * 3
    cooldown_until_index = -1

    # Entry context thresholds
    ma_distance_threshold = 0.00159
    candle_move_threshold = 0.008
    impulse_move_threshold_pct = 1.5
    impulse_lookback = 5
    late_entry_atr_mult = 0.8
    late_entry_body_ratio = 0.8
    late_entry_ema_pct = 0.005

    # Entry/exit controls
    entry_score_threshold = 9
    exit_score_threshold = 6

    slope_window = 5
    trail_activate_pct = 0.007
    trail_retrace_pct = 0.003
    loss_exit_pct = 0.05
    profit_exit_pct = 0.07
    adx_exit_threshold = 15.0
    adx_exit_lookback = 1
    entry_adx_threshold = 20.5
    entry_atr_threshold = 1.2
    opposite_atr_body_mult = 0.6
    sharp_move_threshold_pct = 12.0
    sharp_move_lookback_candles = 600
    post_cross_penalty_candles = 15
    consecutive_losses_stop_until_month = 5

    # Indicator periods
    period_adx = 14
    period_atr = 14
    period_atr_ma = 21
    period_vol_avg = 12
    volume_spike_multiplier = 1.24

    # Matplot setting
    plot_max_candles = 1200   # chart render limit to keep plotting fast (set <=0 for full range)
    plot_end_offset = 0       # drop latest N candles from chart to inspect older windows
    plot_step_candles = 300   # navigation step for loading older/newer windows
    plot_min_zoom_candles = 80       # minimum window size for zoom-in
    plot_max_render_candles = 1600   # when zoomed out, aggregate to this many candles for smoother rendering
    plot_zoom_in_factor = 0.8        # wheel zoom-in multiplier
    plot_zoom_out_factor = 1.6       # wheel zoom-out multiplier (higher = faster reach to full history)
    plot_window_width_scale = 0.94   # near-fullscreen width without forcing true fullscreen
    plot_window_height_scale = 0.90  # near-fullscreen height without forcing true fullscreen
    plot_drag_preview_factor = 0.42  # render fewer candles while dragging for smoother live updates
    plot_drag_update_interval_ms = 16  # target drag refresh cadence (~60Hz upper bound)
    plot_yscale_drag_sensitivity = 0.0030  # right-drag vertical zoom sensitivity

    plot_post_cross_penalty_markers = True  # show yellow markers where post-cross penalty is applied


    # ---- score weights (entry/exit) ----
    # entry positive
    entry_score_cross = 1
    entry_score_ema_vs_ma50 = 3
    entry_score_ma_trend = 1
    entry_score_ma_distance_or_candle = 1
    entry_score_adx = 1
    entry_score_volume = 2
    # entry negative
    entry_late_penalty = 1  # applied as a subtraction


    # exit positive
    exit_score_loss_guard = 2
    exit_score_profit_guard = 2
    exit_score_ema_slope = 1
    exit_score_ema_cross = 3
    exit_score_ma_trend = 1
    exit_score_trailing = 1
    exit_score_adx = 1
    exit_score_opposite_candle = 1
    # exit negative
    post_cross_penalty_score = 3

    def build_score_reason_text(title, reasons, total_score, threshold):
        lines = [title]
        if reasons:
            for reason_label, pts in reasons:
                sign = "+" if pts >= 0 else ""
                lines.append(f"{sign}{pts} | {reason_label}")
        else:
            lines.append("No score components recorded.")
        lines.append("-" * 20)
        lines.append(f"Total Score: {total_score}")
        lines.append(f"Threshold: {threshold}")
        return "\n".join(lines)

    def strongest_directional_moves_pct(prices, start_idx, end_idx):
        """Measure strongest ordered up/down moves in one pass."""
        if end_idx <= start_idx:
            return 0.0, 0.0

        first_price = float(prices[start_idx])
        if not np.isfinite(first_price) or first_price <= 0:
            return 0.0, 0.0

        max_up_move_pct = 0.0
        max_down_move_pct = 0.0
        trough = first_price
        peak = first_price
        for j in range(start_idx + 1, end_idx + 1):
            price = float(prices[j])
            if not np.isfinite(price) or price <= 0:
                continue

            up_move_pct = (price / trough - 1.0) * 100.0
            if up_move_pct > max_up_move_pct:
                max_up_move_pct = up_move_pct
            if price < trough:
                trough = price

            down_move_pct = (peak / price - 1.0) * 100.0
            if down_move_pct > max_down_move_pct:
                max_down_move_pct = down_move_pct
            if price > peak:
                peak = price

        return max_up_move_pct, max_down_move_pct

    # Apply tune overrides (explicit assignments to avoid relying on locals())
    if tune:
        if 'slope_window' in tune:
            slope_window = int(tune['slope_window'])

        if 'entry_score_threshold' in tune:
            entry_score_threshold = int(tune['entry_score_threshold'])

        if 'exit_score_threshold' in tune:
            exit_score_threshold = int(tune['exit_score_threshold'])

        if 'entry_atr_threshold' in tune:
            entry_atr_threshold = float(tune['entry_atr_threshold'])

        if 'period_atr_ma' in tune:
            period_atr_ma = int(tune['period_atr_ma'])

        if 'period_adx' in tune:
            period_adx = int(tune['period_adx'])

        if 'period_atr' in tune:
            period_atr = int(tune['period_atr'])

        if 'period_vol_avg' in tune:
            period_vol_avg = int(tune['period_vol_avg'])

        if 'volume_spike_multiplier' in tune:
            volume_spike_multiplier = float(tune['volume_spike_multiplier'])

        if 'ma_distance_threshold' in tune:
            ma_distance_threshold = float(tune['ma_distance_threshold'])

        if 'candle_move_threshold' in tune:
            candle_move_threshold = float(tune['candle_move_threshold'])

        if 'impulse_move_threshold_pct' in tune:
            impulse_move_threshold_pct = float(tune['impulse_move_threshold_pct'])

        if 'impulse_lookback' in tune:
            impulse_lookback = int(tune['impulse_lookback'])

        if 'late_entry_atr_mult' in tune:
            late_entry_atr_mult = float(tune['late_entry_atr_mult'])

        if 'late_entry_body_ratio' in tune:
            late_entry_body_ratio = float(tune['late_entry_body_ratio'])

        if 'late_entry_ema_pct' in tune:
            late_entry_ema_pct = float(tune['late_entry_ema_pct'])

        if 'trail_activate_pct' in tune:
            trail_activate_pct = float(tune['trail_activate_pct'])

        if 'trail_retrace_pct' in tune:
            trail_retrace_pct = float(tune['trail_retrace_pct'])

        if 'loss_exit_pct' in tune:
            loss_exit_pct = float(tune['loss_exit_pct'])

        if 'profit_exit_pct' in tune:
            profit_exit_pct = float(tune['profit_exit_pct'])

        if 'adx_exit_threshold' in tune:
            adx_exit_threshold = float(tune['adx_exit_threshold'])

        if 'adx_exit_lookback' in tune:
            adx_exit_lookback = int(tune['adx_exit_lookback'])

        if 'entry_adx_threshold' in tune:
            entry_adx_threshold = float(tune['entry_adx_threshold'])

        if 'opposite_atr_body_mult' in tune:
            opposite_atr_body_mult = float(tune['opposite_atr_body_mult'])

        if 'sharp_move_threshold_pct' in tune:
            sharp_move_threshold_pct = float(tune['sharp_move_threshold_pct'])

        if 'sharp_move_lookback_candles' in tune:
            sharp_move_lookback_candles = int(tune['sharp_move_lookback_candles'])

        if 'post_cross_penalty_candles' in tune:
            post_cross_penalty_candles = int(tune['post_cross_penalty_candles'])

        if 'consecutive_losses_stop_until_month' in tune:
            consecutive_losses_stop_until_month = int(tune['consecutive_losses_stop_until_month'])

        if 'post_cross_penalty_score' in tune:
            post_cross_penalty_score = int(tune['post_cross_penalty_score'])

        if 'entry_score_cross' in tune:
            entry_score_cross = int(tune['entry_score_cross'])

        if 'entry_score_ema_vs_ma50' in tune:
            entry_score_ema_vs_ma50 = int(tune['entry_score_ema_vs_ma50'])


        if 'entry_score_ma_trend' in tune:
            entry_score_ma_trend = int(tune['entry_score_ma_trend'])

        if 'entry_score_ma_distance_or_candle' in tune:
            entry_score_ma_distance_or_candle = int(tune['entry_score_ma_distance_or_candle'])

        if 'entry_score_adx' in tune:
            entry_score_adx = int(tune['entry_score_adx'])

        if 'entry_score_volume' in tune:
            entry_score_volume = int(tune['entry_score_volume'])

        if 'entry_late_penalty' in tune:
            entry_late_penalty = int(tune['entry_late_penalty'])

        if 'exit_score_loss_guard' in tune:
            exit_score_loss_guard = int(tune['exit_score_loss_guard'])

        if 'exit_score_profit_guard' in tune:
            exit_score_profit_guard = int(tune['exit_score_profit_guard'])

        if 'exit_score_ema_slope' in tune:
            exit_score_ema_slope = int(tune['exit_score_ema_slope'])

        if 'exit_score_ema_cross' in tune:
            exit_score_ema_cross = int(tune['exit_score_ema_cross'])

        if 'exit_score_ma_trend' in tune:
            exit_score_ma_trend = int(tune['exit_score_ma_trend'])

        if 'exit_score_trailing' in tune:
            exit_score_trailing = int(tune['exit_score_trailing'])

        if 'exit_score_adx' in tune:
            exit_score_adx = int(tune['exit_score_adx'])

        if 'exit_score_opposite_candle' in tune:
            exit_score_opposite_candle = int(tune['exit_score_opposite_candle'])

        if 'trade_amount_percent' in tune:
            trade_amount_percent = float(tune['trade_amount_percent'])

        if 'monthly_profit_percent_stop_trade' in tune:
            monthly_profit_percent_stop_trade = int(tune['monthly_profit_percent_stop_trade'])

        if 'monthly_loss_percent_stop_trade' in tune:
            monthly_loss_percent_stop_trade = int(tune['monthly_loss_percent_stop_trade'])

        if 'monthly_profit_close_filter' in tune:
            monthly_profit_close_filter = bool(tune['monthly_profit_close_filter'])

        if 'monthly_loss_close_filter' in tune:
            monthly_loss_close_filter = bool(tune['monthly_loss_close_filter'])

        if 'adx_filter' in tune:
            adx_filter = bool(tune['adx_filter'])

        if 'volume_filter' in tune:
            volume_filter = bool(tune['volume_filter'])

        if 'consecutive_losses_month_stop_filter' in tune:
            consecutive_losses_month_stop_filter = bool(tune['consecutive_losses_month_stop_filter'])

        if 'skip_logic' in tune:
            skip_logic = bool(tune['skip_logic'])

        if 'leverage' in tune:
            leverage = float(tune['leverage'])

        if 'safe_leverage_low' in tune:
            safe_leverage_low = float(tune['safe_leverage_low'])

        if 'safe_leverage_med' in tune:
            safe_leverage_med = float(tune['safe_leverage_med'])

        if 'safe_leverage_high' in tune:
            safe_leverage_high = float(tune['safe_leverage_high'])

        if 'safe_leverage_balance_pct_low' in tune:
            safe_leverage_balance_pct_low = float(tune['safe_leverage_balance_pct_low'])

        if 'safe_leverage_balance_pct_med' in tune:
            safe_leverage_balance_pct_med = float(tune['safe_leverage_balance_pct_med'])

        if 'safe_leverage_balance_pct_high' in tune:
            safe_leverage_balance_pct_high = float(tune['safe_leverage_balance_pct_high'])

        if 'save_money_recover_trigger_pct' in tune:
            save_money_recover_trigger_pct = float(tune['save_money_recover_trigger_pct'])
            
        if 'cooldown_after_big_pnl' in tune:
            cooldown_after_big_pnl = int(tune['cooldown_after_big_pnl'])

    # ---- setting end ----

    # ---- fee rate ----
    fee_rate = 0.0005  # 0.05% per trade (entry or exit)

    total_wins = 0
    total_liquids = 0
    total_wins_long = 0
    total_wins_short = 0
    total_losses = 0
    total_long = 0
    total_short = 0
    total_profit_percent = 0
    deducting_fee_total = 0
    count_closed_orders = 0
    profit_percent_per_month = 0
    consecutive_losses = 0
    loss_streak_until_month_stop = 0
    stop_trading_until_new_month_by_losses = False
    skip_trades_left = 0
    max_drawdown = 0

    lst_profit_percent_per_month = []

    equity_curve = []
    profits_lst = []
    chart_data = [] if not optimize else None
    # price chart trade markers
    long_open_points = [] if not optimize else None
    long_close_points = [] if not optimize else None
    short_open_points = [] if not optimize else None
    short_close_points = [] if not optimize else None
    long_open_reasons = {} if not optimize else None
    long_close_reasons = {} if not optimize else None
    short_open_reasons = {} if not optimize else None
    short_close_reasons = {} if not optimize else None
    penalty_long_points = [] if (not optimize and plot_post_cross_penalty_markers) else None
    penalty_short_points = [] if (not optimize and plot_post_cross_penalty_markers) else None
    penalty_long_reasons = {} if (not optimize and plot_post_cross_penalty_markers) else None
    penalty_short_reasons = {} if (not optimize and plot_post_cross_penalty_markers) else None

    current_position = None
    entry_price = None
    entry_index = None
    highest_since_entry = None
    lowest_since_entry = None
    position_size = None
    position_size_no_fee = None
    balance_before_trade = None
    balance_before_trade_no_fee = None
    open_time_value = None
    atr_ratio = None

    # ---- Cross & Exit state and parameters ----
    cross_seen = False               # whether EMA16/MA50 have crossed at least once
    last_cross_dir = None           # 'bull' or 'bear'
    last_cross_index = None
    last_cross_strongest_up_move_pct = 0.0
    last_cross_strongest_down_move_pct = 0.0
    last_trade_cross_index = None   # index of the cross used to open the last trade
    trade_power = True

    balance_without_fee = balance
    first_balance = balance
    tactical_balance = first_balance

    first_open_time = open_times[0]
    last_close_time = close_times[-1]

    # ---- Get MA, EMA ----
    indicator = Indicator(close_prices, period=None)

    # MA/EMA
    ema_16_period = 16
    ma_50_period = 50
    ma_100_period = 102
    ma_200_period = 198
    

    # Optimize: MA, EMA
    if tune:
        if 'ema_16' in tune:
            ema_16_period = int(tune['ema_16'])
        if 'ma_50' in tune:
            ma_50_period = int(tune['ma_50'])
        if 'ma_100' in tune:
            ma_100_period = int(tune['ma_100'])
        if 'ma_200' in tune:
            ma_200_period = int(tune['ma_200'])

    ema_16 = _cached_indicator("ema", ema_16_period, lambda: indicator.get_EMA(ema_16_period))
    ma_50 = _cached_indicator("ma", ma_50_period, lambda: indicator.get_MA(ma_50_period))
    ma_100 = _cached_indicator("ma", ma_100_period, lambda: indicator.get_MA(ma_100_period))
    ma_200 = _cached_indicator("ma", ma_200_period, lambda: indicator.get_MA(ma_200_period))



    # ---- MANAGE TRADES ----
    trade_manager = TradeManager(csv_logger, first_balance, monthly_profit_percent_stop_trade,
                                 monthly_loss_percent_stop_trade, tactical_balance, monthly_profit_close_filter,
                                 monthly_loss_close_filter, monthly_compound, leverage, safe_leverage_low,
                                 safe_leverage_med, safe_leverage_high, safe_leverage_balance_pct_low,
                                 safe_leverage_balance_pct_med, safe_leverage_balance_pct_high,
                                 save_money_recover_trigger_pct, verbose=verbose)

    # ---- get_ADX ----
    # reuse existing `indicator` instance (created above) to avoid re-initialization
    adx = _cached_indicator(
        "adx",
        period_adx,
        lambda: indicator.get_ADX(high_prices, low_prices, close_prices, period=period_adx),
    )

    # ---- get_ATR ----
    atr = _cached_indicator(
        "atr",
        period_atr,
        lambda: indicator.get_ATR(high_prices, low_prices, close_prices, period=period_atr),
    )
    # ---- get_ATR_MA ----
    atr_ma = _cached_indicator(
        "atr_ma",
        (period_atr, period_atr_ma),
        lambda: indicator.get_ATR_MA(atr, period=period_atr_ma),
    )
    # ---- get volume average ----
    vol_avg_15_list = _cached_indicator(
        "vol_avg",
        period_vol_avg,
        lambda: indicator.get_volume_avg(volume_prices, period=period_vol_avg),
    )

    # you can use times for open/close orders
    # # ---- time filter mask (13:30 UTC close time) ----
    # close_times_utc = pd.to_datetime(close_times, utc=True)
    # time_1330_mask = (close_times_utc.hour == 13) & (close_times_utc.minute == 30)

    #   # check data loaded correctly :
    # print(len(open_prices), "candles loaded.")
    # print("len(ema_16):", len(ema_16))
    # print("len(ma_50):", len(ma_50))
    # print("len adx:", len(adx))

    # ---- MAIN ----
    for i in range(len(close_prices)):
        # print(start+i)

        if chart_data is not None:
            chart_data.append([i, balance + (margin if current_position is not None else 0) + save_money])

        if ema_16[i] is None or ma_50[i] is None or ma_100[i] is None or ma_200[i] is None:
            continue

        # ----- Detect EMA16 / MA50 crosses (update cross state) -----
        if i > 0 and ema_16[i-1] is not None and ma_50[i-1] is not None:
            # bullish cross: EMA crosses above MA
            if ema_16[i-1] <= ma_50[i-1] and ema_16[i] > ma_50[i]:
                cross_seen = True
                last_cross_dir = 'bull'
                last_cross_index = i
                lookback = max(2, sharp_move_lookback_candles)
                start_idx = max(0, i - (lookback - 1))
                last_cross_strongest_up_move_pct, last_cross_strongest_down_move_pct = strongest_directional_moves_pct(
                    close_prices, start_idx, i
                )
            # bearish cross: EMA crosses below MA
            elif ema_16[i-1] >= ma_50[i-1] and ema_16[i] < ma_50[i]:
                cross_seen = True
                last_cross_dir = 'bear'
                last_cross_index = i
                lookback = max(2, sharp_move_lookback_candles)
                start_idx = max(0, i - (lookback - 1))
                last_cross_strongest_up_move_pct, last_cross_strongest_down_move_pct = strongest_directional_moves_pct(
                    close_prices, start_idx, i
                )

        # stop trading after N consecutive losses until next month starts
        if consecutive_losses_month_stop_filter and stop_trading_until_new_month_by_losses:
            if int(start + i) in lst_month_starts:
                stop_trading_until_new_month_by_losses = False
                loss_streak_until_month_stop = 0
            else:
                continue
        
        # monthly filter if profit/loss monthly stop toggles are active
        if monthly_profit_close_filter or monthly_loss_close_filter:
            if trade_power == False:
                if int(start+i) in lst_month_starts:
                    lst_profit_percent_per_month.append(profit_percent_per_month)
                    profit_percent_per_month = 0
                    trade_power = True 
                else:
                    continue
        
        # cooldown after good profit
        if i < cooldown_until_index:
            continue
        
        # Calculate MA Distance
        ma_distance = abs(ema_16[i] - ma_50[i]) / ma_50[i]

        # Calculate Distance New Candle Move and Last Candle Move
        if i > 0:
            last_candle_move = abs(close_prices[i] - open_prices[i]) / open_prices[i]
        else:
            last_candle_move = 0

        # Calculate total balance (if we have order we have: margin + balance)
        margin_balance = balance + (margin if current_position is not None else 0)

        # ===================== CHECK LIQUIDATION =====================
        # --- check long
        if current_position == "long":
            liq_updates = trade_manager.check_liquidation_long(
                i,
                low_prices,
                close_times,
                entry_price,
                leverage,
                margin,
                margin_no_fee,
                balance_before_trade,
                balance_before_trade_no_fee,
                balance,
                balance_without_fee,
                deducting_fee_total,
                count_closed_orders,
                total_losses,
                total_long,
                equity_curve,
                save_money,
                max_drawdown,
                open_time_value,
                csv_logger,
                trade_amount_percent,
                profit_percent_per_month,
                total_liquids
            )

            if liq_updates['liquidated']:
                liq_reason_text = "LONG EXIT (Liquidation)\nForced close by liquidation rule."
                balance = liq_updates['balance']
                balance_without_fee = liq_updates['balance_without_fee']
                deducting_fee_total = liq_updates['deducting_fee_total']
                count_closed_orders = liq_updates['count_closed_orders']
                total_losses = liq_updates['total_losses']
                total_long = liq_updates['total_long']
                equity_curve = liq_updates['equity_curve']
                max_drawdown = liq_updates['max_drawdown']
                total_liquids = liq_updates['total_liquids']
                if consecutive_losses_month_stop_filter:
                    loss_streak_until_month_stop += 1
                    if (
                        consecutive_losses_stop_until_month > 0
                        and loss_streak_until_month_stop >= consecutive_losses_stop_until_month
                    ):
                        stop_trading_until_new_month_by_losses = True
                        loss_streak_until_month_stop = 0
                current_position = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if long_close_points is not None:
                    long_close_points.append((i, liq_updates['close_price']))
                    if long_close_reasons is not None:
                        long_close_reasons[i] = liq_reason_text
                continue
        
        # ---- check short
        if current_position == "short":
            liq_updates = trade_manager.check_liquidation_short(
                i,
                high_prices,
                close_times,
                entry_price,
                leverage,
                margin,
                margin_no_fee,
                balance_before_trade,
                balance_before_trade_no_fee,
                balance,
                balance_without_fee,
                deducting_fee_total,
                count_closed_orders,
                total_losses,
                total_short,
                equity_curve,
                save_money,
                max_drawdown,
                open_time_value,
                csv_logger,
                trade_amount_percent,
                profit_percent_per_month,
                total_liquids
            )

            if liq_updates['liquidated']:
                liq_reason_text = "SHORT EXIT (Liquidation)\nForced close by liquidation rule."
                balance = liq_updates['balance']
                balance_without_fee = liq_updates['balance_without_fee']
                deducting_fee_total = liq_updates['deducting_fee_total']
                count_closed_orders = liq_updates['count_closed_orders']
                total_losses = liq_updates['total_losses']
                total_short = liq_updates['total_short']
                equity_curve = liq_updates['equity_curve']
                max_drawdown = liq_updates['max_drawdown']
                total_liquids = liq_updates['total_liquids']
                if consecutive_losses_month_stop_filter:
                    loss_streak_until_month_stop += 1
                    if (
                        consecutive_losses_stop_until_month > 0
                        and loss_streak_until_month_stop >= consecutive_losses_stop_until_month
                    ):
                        stop_trading_until_new_month_by_losses = True
                        loss_streak_until_month_stop = 0
                current_position = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if short_close_points is not None:
                    short_close_points.append((i, liq_updates['close_price']))
                    if short_close_reasons is not None:
                        short_close_reasons[i] = liq_reason_text
                continue


        # ===================== OPEN LONG =====================
        # Require that EMA/MA50 have crossed and the last cross was bullish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:

                entry_score = 0
                entry_reasons = []

                # ===== ATR ENTRY FILTER =====
                if atr_filter == True:
                    if atr[i] is None or atr_ma[i] is None:
                        continue

                    atr_ratio = atr[i] / atr_ma[i]

                    if atr_ratio < entry_atr_threshold:
                        continue

                # ---- positive scores
                # 1) CONFIRMED BULL CROSS
                if last_cross_dir == 'bull' and last_cross_index is not None:
                    # wait at least 1 candle after cross
                    if i > last_cross_index:
                        # price acceptance above EMA after cross
                        if close_prices[i] > ema_16[i]:
                            entry_score += entry_score_cross
                            entry_reasons.append(("Bull cross confirmed above EMA16", entry_score_cross))
                # 2) EMA 14 > Ma 50
                if ema_16[i] > ma_50[i]:
                    entry_score += entry_score_ema_vs_ma50
                    entry_reasons.append(("EMA16 above MA50", entry_score_ema_vs_ma50))
                # 3) Ma 130 > Ma 200
                if ma_100[i] >= ma_200[i]:
                    entry_score += entry_score_ma_trend
                    entry_reasons.append(("MA100 above/equal MA200", entry_score_ma_trend))
                # 4) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += entry_score_ma_distance_or_candle
                    entry_reasons.append(("Momentum strength (MA distance or candle move)", entry_score_ma_distance_or_candle))
                # 5) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] != None and adx[i] >= entry_adx_threshold:
                        entry_score += entry_score_adx
                        entry_reasons.append(("ADX strength confirmation", entry_score_adx))
                # 6) ===== VOLUME FILTER =====
                if volume_filter:
                    vol_now = volume_prices[i]
                    vol_avg15 = vol_avg_15_list[i]
                    if vol_now >= volume_spike_multiplier * vol_avg15:
                        entry_score += entry_score_volume
                        entry_reasons.append(("Volume spike confirmation", entry_score_volume))
                # ---- negative scores (late-entry guard)
                # only penalize when a sharp move already happened AND price is overextended AND momentum is cooling
                if i >= impulse_lookback:
                    impulse_pct = (close_prices[i] / close_prices[i - impulse_lookback] - 1.0) * 100
                    if impulse_pct > impulse_move_threshold_pct:
                        if atr[i] is not None and atr[i] > 0:
                            extension = (close_prices[i] - ema_16[i]) / atr[i]
                            overextended = extension > late_entry_atr_mult
                        else:
                            extension = (close_prices[i] - ema_16[i]) / ema_16[i]
                            overextended = extension > late_entry_ema_pct

                        body_now = close_prices[i] - open_prices[i]
                        body_prev = close_prices[i - 1] - open_prices[i - 1]
                        cooling = (body_now <= 0) or (body_prev > 0 and body_now < body_prev * late_entry_body_ratio)

                        if overextended and cooling:
                            entry_score -= entry_late_penalty
                            entry_reasons.append(("Late-entry penalty: overextended + cooling", -entry_late_penalty))

                if entry_score >= entry_score_threshold:
                    entry_reason_text = build_score_reason_text(
                        "LONG ENTRY SCORE REASONS",
                        entry_reasons,
                        entry_score,
                        entry_score_threshold,
                    )
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
                        if verbose:
                            print(f"⏭️ SKIP LONG | skips left: {skip_trades_left}")
                        continue

                    # ---- open long ----
                    updates = trade_manager.open_long(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        first_balance,
                        trade_amount_percent,
                        margin_balance,
                        leverage)
                    

                    entry_price = updates['entry_price']
                    balance = updates['balance']
                    balance_without_fee = updates['balance_without_fee']
                    balance_before_trade = updates['balance_before_trade']
                    balance_before_trade_no_fee = updates['balance_before_trade_no_fee']
                    margin = updates['margin']
                    leverage = updates['leverage']
                    position_size = updates['position_size']
                    margin_no_fee = updates['margin_no_fee']
                    position_size_no_fee = updates['position_size_no_fee']
                    open_time_value = updates['open_time_value']
                    current_position = updates['current_position']
                    if long_open_points is not None:
                        long_open_points.append((i, entry_price))
                        if long_open_reasons is not None:
                            long_open_reasons[i] = entry_reason_text
                    # record which cross enabled this trade and init trailing state
                    last_trade_cross_index = last_cross_index
                    entry_index = i
                    highest_since_entry = max(entry_price, high_prices[i])
                    lowest_since_entry = min(entry_price, low_prices[i])

                    updates = None


        # ===================== CLOSE LONG =====================
        if current_position == "long":
            # exit scoring system (points accumulate; mirrored for short)
            exit_score = 0
            exit_reasons = []

            # update trailing peak
            if highest_since_entry is None:
                highest_since_entry = entry_price
            if high_prices[i] > highest_since_entry:
                highest_since_entry = high_prices[i]

            # 0) loss guard (no leverage): if price drops >= loss_exit_pct from entry
            if entry_price is not None:
                if close_prices[i] <= entry_price * (1 - loss_exit_pct):
                    exit_score += exit_score_loss_guard
                    exit_reasons.append(("Loss guard triggered", exit_score_loss_guard))

            # 1) profit guard (no leverage): if price rises >= profit_exit_pct from entry
            if entry_price is not None:
                if close_prices[i] >= entry_price * (1 + profit_exit_pct):
                    exit_score += exit_score_profit_guard
                    exit_reasons.append(("Profit guard triggered", exit_score_profit_guard))

            # 2) EMA slope weakness (look back `slope_window` candles)
            if i - slope_window >= 0 and ema_16[i] < ema_16[i - slope_window]:
                exit_score += exit_score_ema_slope
                exit_reasons.append(("EMA16 slope weakness", exit_score_ema_slope))

            # 3) EMA crossing below MA50
            if ema_16[i] < ma_50[i]:
                exit_score += exit_score_ema_cross
                exit_reasons.append(("EMA16 crossed below MA50", exit_score_ema_cross))

            # 4) long-term trend weakening (MA100 < MA200)
            if ma_100[i] < ma_200[i]:
                exit_score += exit_score_ma_trend
                exit_reasons.append(("MA100 below MA200", exit_score_ma_trend))

            # 5) trailing stop based on pullback from peak (armed after min profit)
            if entry_index is not None and i > entry_index:
                if highest_since_entry >= entry_price * (1 + trail_activate_pct):
                    if close_prices[i] <= highest_since_entry * (1 - trail_retrace_pct):
                        exit_score += exit_score_trailing
                        exit_reasons.append(("Trailing retrace exit", exit_score_trailing))

            # 6) ADX weakening (trend strength fading)
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += exit_score_adx
                            exit_reasons.append(("ADX weakening", exit_score_adx))

            # 7) strong opposite candle (body >= ATR * mult)
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] < open_prices[i]:
                    body = open_prices[i] - close_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += exit_score_opposite_candle
                        exit_reasons.append(("Strong opposite bearish candle", exit_score_opposite_candle))
            
            # ---- negative scores
            # 0) temporary post-cross penalty after a sharp move (LONG only)
            if last_cross_index is not None and i > last_cross_index and post_cross_penalty_candles > 0:
                candles_since_cross = i - last_cross_index
                if (
                    last_cross_strongest_up_move_pct >= sharp_move_threshold_pct
                    and candles_since_cross < post_cross_penalty_candles
                    and ema_16[i] < ma_50[i]
                ):
                    exit_score -= post_cross_penalty_score
                    penalty_reason_text = (
                        f"Post-cross sharp-move penalty ({candles_since_cross} candles since cross, "
                        f"up-move={last_cross_strongest_up_move_pct:.2f}%)"
                    )
                    exit_reasons.append((
                        penalty_reason_text,
                        -post_cross_penalty_score,
                    ))
                    if penalty_long_points is not None:
                        penalty_long_points.append((i, close_prices[i]))
                        if penalty_long_reasons is not None:
                            penalty_long_reasons[i] = (
                                f"LONG penalty marker\n{penalty_reason_text}\nScore impact: -{post_cross_penalty_score}"
                            )

            if exit_score >= exit_score_threshold:
                exit_reason_text = build_score_reason_text(
                    "LONG EXIT SCORE REASONS",
                    exit_reasons,
                    exit_score,
                    exit_score_threshold,
                )
                # ---- close long ----
                close_price = close_prices[i]
                updates = trade_manager.close_long(
                    i,
                    close_prices,
                    close_times,
                    entry_price,
                    position_size,
                    position_size_no_fee,
                    fee_rate,
                    margin,
                    margin_no_fee,
                    balance,
                    balance_without_fee,
                    balance_before_trade,
                    balance_before_trade_no_fee,
                    deducting_fee_total,
                    profits_lst,
                    total_profit_percent,
                    count_closed_orders,
                    equity_curve,
                    max_drawdown,
                    total_wins,
                    total_wins_long,
                    total_losses,
                    total_long,
                    cooldown_after_big_pnl,
                    leverage,
                    cooldown_until_index,
                    open_time_value,
                    csv_logger,
                    trade_amount_percent,
                    profit_percent_per_month,
                    save_money,
                    trade_power)

                balance = updates['balance']
                balance_without_fee = updates['balance_without_fee']
                deducting_fee_total = updates['deducting_fee_total']
                profits_lst = updates['profits_lst']
                total_profit_percent = updates['total_profit_percent']
                count_closed_orders = updates['count_closed_orders']
                equity_curve = updates['equity_curve']
                max_drawdown = updates['max_drawdown']
                total_wins = updates['total_wins']
                total_wins_long = updates['total_wins_long']
                total_losses = updates['total_losses']
                total_long = updates['total_long']
                cooldown_until_index = updates['cooldown_until_index']
                current_position = updates['current_position']
                profit_percent_per_month = updates['profit_percent_per_month']
                save_money = updates['save_money']
                trade_power = updates['trade_power']
                updates = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if long_close_points is not None:
                    long_close_points.append((i, close_price))
                    if long_close_reasons is not None:
                        long_close_reasons[i] = exit_reason_text
                
                # count consecutive_losses 
                if profits_lst[-1] < 0:
                    consecutive_losses += 1
                    if consecutive_losses_month_stop_filter:
                        loss_streak_until_month_stop += 1
                        if (
                            consecutive_losses_stop_until_month > 0
                            and loss_streak_until_month_stop >= consecutive_losses_stop_until_month
                        ):
                            stop_trading_until_new_month_by_losses = True
                            loss_streak_until_month_stop = 0
                else:
                    consecutive_losses = 0
                    if consecutive_losses_month_stop_filter:
                        loss_streak_until_month_stop = 0

                if consecutive_losses >= 2:
                    skip_trades_left = 2
                    consecutive_losses = 0

        # ===================== OPEN SHORT =====================
        # Require that EMA/MA50 have crossed and the last cross was bearish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:
                
                entry_score = 0
                entry_reasons = []
                
                # ===== ATR ENTRY FILTER =====
                if atr_filter == True:
                    if atr[i] is None or atr_ma[i] is None:
                        continue

                    atr_ratio = atr[i] / atr_ma[i]

                    if atr_ratio < entry_atr_threshold:
                        continue
                # ---- positive scores
                # 1) CONFIRMED BEAR CROSS
                if last_cross_dir == 'bear' and last_cross_index is not None:
                    # wait at least 1 candle after cross
                    if i > last_cross_index:
                        # price acceptance below EMA after cross
                        if close_prices[i] < ema_16[i]:
                            entry_score += entry_score_cross
                            entry_reasons.append(("Bear cross confirmed below EMA16", entry_score_cross))
                # 2) EMA 14 < Ma 50
                if ema_16[i] <= ma_50[i]:
                    entry_score += entry_score_ema_vs_ma50
                    entry_reasons.append(("EMA16 below/equal MA50", entry_score_ema_vs_ma50))
                # 3) Ma 130 < Ma 200
                if ma_100[i] < ma_200[i]:
                    entry_score += entry_score_ma_trend
                    entry_reasons.append(("MA100 below MA200", entry_score_ma_trend))
                # 4) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += entry_score_ma_distance_or_candle
                    entry_reasons.append(("Momentum strength (MA distance or candle move)", entry_score_ma_distance_or_candle))
                # 5) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] != None and adx[i] >= entry_adx_threshold:
                        entry_score += entry_score_adx
                        entry_reasons.append(("ADX strength confirmation", entry_score_adx))
                # 6) ===== VOLUME FILTER =====
                if volume_filter:
                    vol_now = volume_prices[i]
                    vol_avg15 = vol_avg_15_list[i]
                    if vol_now >= volume_spike_multiplier * vol_avg15:
                        entry_score += entry_score_volume
                        entry_reasons.append(("Volume spike confirmation", entry_score_volume))
                # ---- negative scores (late-entry guard)
                # only penalize when a sharp move already happened AND price is overextended AND momentum is cooling
                if i >= impulse_lookback:
                    impulse_pct = (close_prices[i - impulse_lookback] / close_prices[i] - 1.0) * 100
                    if impulse_pct > impulse_move_threshold_pct:
                        if atr[i] is not None and atr[i] > 0:
                            extension = (ema_16[i] - close_prices[i]) / atr[i]
                            overextended = extension > late_entry_atr_mult
                        else:
                            extension = (ema_16[i] - close_prices[i]) / ema_16[i]
                            overextended = extension > late_entry_ema_pct

                        body_now = close_prices[i] - open_prices[i]
                        body_prev = close_prices[i - 1] - open_prices[i - 1]
                        cooling = (body_now >= 0) or (body_prev < 0 and abs(body_now) < abs(body_prev) * late_entry_body_ratio)

                        if overextended and cooling:
                            entry_score -= entry_late_penalty
                            entry_reasons.append(("Late-entry penalty: overextended + cooling", -entry_late_penalty))


                if entry_score >= entry_score_threshold:
                    entry_reason_text = build_score_reason_text(
                        "SHORT ENTRY SCORE REASONS",
                        entry_reasons,
                        entry_score,
                        entry_score_threshold,
                    )
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
                        if verbose:
                            print(f"⏭️ SKIP SHORT | skips left: {skip_trades_left}")
                        continue

                    # ---- open short ----
                    updates = trade_manager.open_short(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        first_balance,
                        trade_amount_percent,
                        margin_balance,
                        leverage)
                    

                    entry_price = updates['entry_price']
                    balance = updates['balance']
                    balance_without_fee = updates['balance_without_fee']
                    balance_before_trade = updates['balance_before_trade']
                    balance_before_trade_no_fee = updates['balance_before_trade_no_fee']
                    margin = updates['margin']
                    leverage = updates['leverage']
                    position_size = updates['position_size']
                    margin_no_fee = updates['margin_no_fee']
                    position_size_no_fee = updates['position_size_no_fee']
                    open_time_value = updates['open_time_value']
                    current_position = updates['current_position']
                    if short_open_points is not None:
                        short_open_points.append((i, entry_price))
                        if short_open_reasons is not None:
                            short_open_reasons[i] = entry_reason_text
                    # record which cross enabled this trade and init trailing state
                    last_trade_cross_index = last_cross_index
                    entry_index = i
                    highest_since_entry = max(entry_price, high_prices[i])
                    lowest_since_entry = min(entry_price, low_prices[i])

                    updates = None


        # ===================== CLOSE SHORT =====================
        if current_position == "short":
            # exit scoring (mirrored logic)
            exit_score = 0
            exit_reasons = []

            # update trailing trough
            if lowest_since_entry is None:
                lowest_since_entry = entry_price
            if low_prices[i] < lowest_since_entry:
                lowest_since_entry = low_prices[i]

            # 0) loss guard (no leverage): if price rises >= loss_exit_pct from entry
            if entry_price is not None:
                if close_prices[i] >= entry_price * (1 + loss_exit_pct):
                    exit_score += exit_score_loss_guard
                    exit_reasons.append(("Loss guard triggered", exit_score_loss_guard))

            # 1) profit guard (no leverage): if price drops >= profit_exit_pct from entry
            if entry_price is not None:
                if close_prices[i] <= entry_price * (1 - profit_exit_pct):
                    exit_score += exit_score_profit_guard
                    exit_reasons.append(("Profit guard triggered", exit_score_profit_guard))

            # 2) EMA slope weakness for short (EMA trending up)
            if i - slope_window >= 0 and ema_16[i] > ema_16[i - slope_window]:
                exit_score += exit_score_ema_slope
                exit_reasons.append(("EMA16 slope weakness (short)", exit_score_ema_slope))

            # 3) EMA crossing above MA50
            if ema_16[i] > ma_50[i]:
                exit_score += exit_score_ema_cross
                exit_reasons.append(("EMA16 crossed above MA50", exit_score_ema_cross))

            # 4) long-term trend weakening for short (MA100 >= MA200)
            if ma_100[i] >= ma_200[i]:
                exit_score += exit_score_ma_trend
                exit_reasons.append(("MA100 above/equal MA200", exit_score_ma_trend))

            # 5) trailing stop based on pullback from trough (armed after min profit)
            if entry_index is not None and i > entry_index:
                if lowest_since_entry <= entry_price * (1 - trail_activate_pct):
                    if close_prices[i] >= lowest_since_entry * (1 + trail_retrace_pct):
                        exit_score += exit_score_trailing
                        exit_reasons.append(("Trailing retrace exit", exit_score_trailing))

            # 6) ADX weakening (trend strength fading)
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += exit_score_adx
                            exit_reasons.append(("ADX weakening", exit_score_adx))

            # 7) strong opposite candle (body >= ATR * mult)
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] > open_prices[i]:
                    body = close_prices[i] - open_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += exit_score_opposite_candle
                        exit_reasons.append(("Strong opposite bullish candle", exit_score_opposite_candle))

            # ---- negative scores
            # 0) temporary post-cross penalty after a sharp move (SHORT mirror)
            if last_cross_index is not None and i > last_cross_index and post_cross_penalty_candles > 0:
                candles_since_cross = i - last_cross_index
                if (
                    last_cross_strongest_down_move_pct >= sharp_move_threshold_pct
                    and candles_since_cross < post_cross_penalty_candles
                    and ema_16[i] > ma_50[i]
                ):
                    exit_score -= post_cross_penalty_score
                    penalty_reason_text = (
                        f"Post-cross sharp-move penalty ({candles_since_cross} candles since cross, "
                        f"down-move={last_cross_strongest_down_move_pct:.2f}%)"
                    )
                    exit_reasons.append((
                        penalty_reason_text,
                        -post_cross_penalty_score,
                    ))
                    if penalty_short_points is not None:
                        penalty_short_points.append((i, close_prices[i]))
                        if penalty_short_reasons is not None:
                            penalty_short_reasons[i] = (
                                f"SHORT penalty marker\n{penalty_reason_text}\nScore impact: -{post_cross_penalty_score}"
                            )

            if exit_score >= exit_score_threshold:
                exit_reason_text = build_score_reason_text(
                    "SHORT EXIT SCORE REASONS",
                    exit_reasons,
                    exit_score,
                    exit_score_threshold,
                )
                # ---- close short ----
                close_price = close_prices[i]
                updates = trade_manager.close_short(
                    i,
                    close_prices,
                    close_times,
                    entry_price,
                    position_size,
                    position_size_no_fee,
                    fee_rate,
                    margin,
                    margin_no_fee,
                    balance,
                    balance_without_fee,
                    balance_before_trade,
                    balance_before_trade_no_fee,
                    deducting_fee_total,
                    profits_lst,
                    total_profit_percent,
                    count_closed_orders,
                    equity_curve,
                    max_drawdown,
                    total_wins,
                    total_wins_short,
                    total_losses,
                    total_short,
                    cooldown_after_big_pnl,
                    leverage,
                    cooldown_until_index,
                    open_time_value,
                    csv_logger,
                    trade_amount_percent,
                    profit_percent_per_month,
                    save_money,
                    trade_power
                    )
                
                balance = updates['balance']
                balance_without_fee = updates['balance_without_fee']
                deducting_fee_total = updates['deducting_fee_total']
                profits_lst = updates['profits_lst']
                total_profit_percent = updates['total_profit_percent']
                count_closed_orders = updates['count_closed_orders']
                equity_curve = updates['equity_curve']
                max_drawdown = updates['max_drawdown']
                total_wins = updates['total_wins']
                total_wins_short = updates['total_wins_short']
                total_losses = updates['total_losses']
                total_short = updates['total_short']
                cooldown_until_index = updates['cooldown_until_index']
                current_position = updates['current_position']
                profit_percent_per_month = updates['profit_percent_per_month']
                save_money = updates['save_money']
                trade_power = updates['trade_power']
                updates = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if short_close_points is not None:
                    short_close_points.append((i, close_price))
                    if short_close_reasons is not None:
                        short_close_reasons[i] = exit_reason_text
                
                # count consecutive_losses 
                if profits_lst[-1] < 0:
                    consecutive_losses += 1
                    if consecutive_losses_month_stop_filter:
                        loss_streak_until_month_stop += 1
                        if (
                            consecutive_losses_stop_until_month > 0
                            and loss_streak_until_month_stop >= consecutive_losses_stop_until_month
                        ):
                            stop_trading_until_new_month_by_losses = True
                            loss_streak_until_month_stop = 0
                else:
                    consecutive_losses = 0
                    if consecutive_losses_month_stop_filter:
                        loss_streak_until_month_stop = 0

                if consecutive_losses >= 2:
                    skip_trades_left = 2
                    consecutive_losses = 0

    # ===================== BACKTEST SUMMARY =====================

    if current_position is not None:
        balance += margin  # return margin if position still open
        balance_without_fee += margin_no_fee # return margin if position still open

    balance += save_money

    # summary calculation
    t_profit_percent = balance * 100 / first_balance - 100
    days, hours, minutes = trade_duration(first_open_time, last_close_time)
    win_rate = (total_wins / (total_wins + total_losses)) * 100 if (total_wins + total_losses) > 0 else 0


    profit_months_count = sum(1 for p in lst_profit_percent_per_month if p > 0)
    loss_months_count = sum(1 for p in lst_profit_percent_per_month if p < 0)

    if verbose:
        print("✅ BACKTEST FINISHED")
        print("Closed Trades:", count_closed_orders, "( Longs:", total_long, "| Shorts:", total_short, ")")
        print("Total Wins:", total_wins, "| Total Wins Long:", total_wins_long, "| Total Wins Short:", total_wins_short)
        print("Total Losses:", total_losses)
        print("Final Balance:", round(balance, 2), "$")
        print("Final Balance (No Fee):", round(balance_without_fee, 2), "$")
        print("Total Fees Paid:", round(deducting_fee_total, 2), "$")
        print("Fee Compounding Impact:",
              round(balance_without_fee - balance - deducting_fee_total, 2), "$")
        print("Maximum Drawdown:", round(max_drawdown, 2), "%")
        print(f"Total Duration : {days} days, {hours} hours, {minutes} minutes")
        print("Win Rate:", round(win_rate, 2), "%")
        print("Total Profit:", round(sum(profits_lst), 2), "$")
        print("Total Profit Percent:", round(t_profit_percent, 2), "%", "or", round(total_profit_percent, 2), "%")
        print("saved Money:", round(save_money,2), "$")
        print("Count Liquids:", total_liquids)
        print("count_profit_months:", profit_months_count)
        print("count_loss_months:", loss_months_count)

    csv_logger.save_csv(
    first_balance=first_balance,
    final_balance=balance,
    total_profit=sum(profits_lst),
    total_profit_percent=t_profit_percent,
    total_fee=deducting_fee_total,
    start_time=first_open_time,
    end_time=last_close_time,
    days=days,
    hours=hours,
    minutes=minutes,
    file_name=os.path.join("outputs", "trades", "data_orders.csv"),
    )

    # optimize already determined earlier; skip plotting when optimizing
    # Draw diagram with OHLC candles (Open/High/Low/Close)
    if optimize is False:
        empty_result = render_backtest_chart(
            chart_data=chart_data,
            close_prices=close_prices,
            close_times=close_times,
            open_prices=open_prices,
            high_prices=high_prices,
            low_prices=low_prices,
            ema_16=ema_16,
            ma_50=ma_50,
            ma_100=ma_100,
            ma_200=ma_200,
            long_open_points=long_open_points,
            long_close_points=long_close_points,
            short_open_points=short_open_points,
            short_close_points=short_close_points,
            penalty_long_points=penalty_long_points,
            penalty_short_points=penalty_short_points,
            long_open_reasons=long_open_reasons,
            long_close_reasons=long_close_reasons,
            short_open_reasons=short_open_reasons,
            short_close_reasons=short_close_reasons,
            penalty_long_reasons=penalty_long_reasons,
            penalty_short_reasons=penalty_short_reasons,
            plot_end_offset=plot_end_offset,
            plot_max_candles=plot_max_candles,
            plot_step_candles=plot_step_candles,
            plot_min_zoom_candles=plot_min_zoom_candles,
            plot_max_render_candles=plot_max_render_candles,
            plot_zoom_in_factor=plot_zoom_in_factor,
            plot_zoom_out_factor=plot_zoom_out_factor,
            plot_window_width_scale=plot_window_width_scale,
            plot_window_height_scale=plot_window_height_scale,
            plot_drag_preview_factor=plot_drag_preview_factor,
            plot_drag_update_interval_ms=plot_drag_update_interval_ms,
            plot_yscale_drag_sensitivity=plot_yscale_drag_sensitivity,
            balance=balance,
            profits_lst=profits_lst,
            t_profit_percent=t_profit_percent,
            count_closed_orders=count_closed_orders,
            total_wins=total_wins,
            total_losses=total_losses,
            max_drawdown=max_drawdown,
            lst_profit_percent_per_month=lst_profit_percent_per_month,
        )
        if empty_result is not None:
            return empty_result
    # generate monthly summary CSV silently (no terminal output)
    if not optimize:
        try:
            write_monthly_summary(
                in_file=os.path.join("outputs", "trades", "data_orders.csv"),
                out_file=os.path.join("outputs", "monthly", "monthly_data_orders.csv"),
                quiet=True,
            )
        except Exception:
            # avoid crashing the backtest if monthly summary fails
            pass

    # return summary metrics for programmatic use
    return {
        'final_balance': balance,
        'total_profit': round(sum(profits_lst), 6),
        'total_profit_percent': round(t_profit_percent, 6),
        'closed_trades': count_closed_orders,
        'wins': total_wins,
        'losses': total_losses,
        'maximum_drawdown': round(max_drawdown, 2),
        'win_rate': round(win_rate, 2),
        "profit_more_than_8%": profit_months_count,
        "profit_months": profit_months_count,
        "loss_months": loss_months_count
    }


    # Run the trading logic when executed as a script
if __name__ == "__main__":
    ma_strategy()

# print(open_prices[0])
# print(open_times[0])
# print(open_times[1])
# print(start, end)
# print(lst_month_starts)
# print(get_candle_index("2025-03-01"))
# print(get_candle_index("2025-02-27"))
