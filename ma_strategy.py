# NOTE: Strategy executes With candle Open prices, High prices, Low prices, Close prices

import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib import transforms as mtransforms
import time
import numpy as np

# My Codes :
from trade_csv_logger import TradeCSVLogger
from indicators import Indicator
from get_candle_index import get_candle_index, get_month_start_indices
from trademanager import TradeManager
from check_monthly_data import write_monthly_summary


# start = get_candle_index("2025-01-01")   ----> 244944
# end = get_candle_index("2025-12-18")     ----> 278640

# get (index or ID) of start, end of csv
start, end = get_candle_index(("2025-12-28","2026-02-14"), ("00:00", "14:00"))
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
    csv_logger = TradeCSVLogger(optimize=optimize)

    # ---- settings is here ----
    balance = 1000     # base balance
    leverage = 10      # leverage
    safe_leverage_high = 4      # leverage safe mode high
    safe_leverage_med = 3      # leverage safe mode medium
    safe_leverage_low = 2      # leverage safe mode low
    save_money = 0
    trade_amount_percent = 0.5  # 50% of balance per trade
    monthly_profit_percent_stop_trade = 8    # if 8% per month profit --> don't trade on that month 
    monthly_compound = 3    # after get 'monthly_profit_percent_stop_trade' per month how much money goes for next month
    monthly_close_filter = True
    adx_filter = True
    volume_filter = True
    atr_filter = True
    skip_logic = False
    
    cooldown_after_big_pnl = 4 * 3  # [4 * 26] [4 * 3]  is good  # number of skip candles
    cooldown_until_index = -1        # best of cooldown_after_big_pnl: 4*12 , 4*46

    ma_distance_threshold = 0.00159  # 0.16٪
    candle_move_threshold = 0.008 # 0.8٪

    impulse_move_threshold_pct = 1.5
    impulse_lookback = 5          # candles to measure sharp move
    late_entry_atr_mult = 0.8     # overextension vs ATR
    late_entry_body_ratio = 0.6   # current body must be <= 60% of prior body to be "cooling"
    late_entry_ema_pct = 0.005    # fallback overextension vs EMA when ATR missing (0.5%)

    # Entry/exit tuning (avoid magic numbers; tweakable)
    slope_window = 5                # candles for EMA slope check
    entry_score_threshold = 10       # points required to trigger entry
    exit_score_threshold = 6        # points required to trigger exit
    trail_activate_pct = 0.007      # arm trailing after +0.7% move from entry
    trail_retrace_pct = 0.003       # exit if price retraces 0.3% from peak
    loss_exit_pct = 0.06            # add 1 exit point if loss reaches 6% (no leverage)
    adx_exit_threshold = 15.0       # trend strength fade threshold
    adx_exit_lookback = 1           # confirm ADX is falling vs N candles ago
    entry_adx_threshold = 20.5      # ADX threshold for entry score confirmation
    entry_atr_threshold = 1.2       # 1, 1.1, 1.2, 1.3 should be test
    opposite_atr_body_mult = 0.6    # strong opposite candle body vs ATR
    period_adx = 14
    period_atr = 14
    period_atr_ma = 21
    period_vol_avg = 12
    volume_spike_multiplier = 1.24  # volume confirmation threshold: vol_now >= multiplier * vol_avg
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
    
    # ---- score weights (entry/exit) ----
    # entry positive
    entry_score_cross = 1
    entry_score_ema_vs_ma50 = 3
    entry_score_close_vs_ema16 = 1
    entry_score_ma_trend = 1
    entry_score_ma_distance_or_candle = 1
    entry_score_adx = 1
    entry_score_volume = 2
    # entry negative
    entry_late_penalty = 1  # applied as a subtraction

    # exit positive
    exit_score_loss_guard = 3
    exit_score_ema_slope = 1
    exit_score_ema_cross = 3
    exit_score_ma_trend = 1
    exit_score_trailing = 1
    exit_score_adx = 1
    exit_score_opposite_candle = 1
    
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

        if 'adx_exit_threshold' in tune:
            adx_exit_threshold = float(tune['adx_exit_threshold'])

        if 'adx_exit_lookback' in tune:
            adx_exit_lookback = int(tune['adx_exit_lookback'])

        if 'entry_adx_threshold' in tune:
            entry_adx_threshold = float(tune['entry_adx_threshold'])

        if 'opposite_atr_body_mult' in tune:
            opposite_atr_body_mult = float(tune['opposite_atr_body_mult'])

        if 'entry_score_cross' in tune:
            entry_score_cross = int(tune['entry_score_cross'])

        if 'entry_score_ema_vs_ma50' in tune:
            entry_score_ema_vs_ma50 = int(tune['entry_score_ema_vs_ma50'])

        if 'entry_score_close_vs_ema16' in tune:
            entry_score_close_vs_ema16 = int(tune['entry_score_close_vs_ema16'])

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

        if 'monthly_close_filter' in tune:
            monthly_close_filter = bool(tune['monthly_close_filter'])

        if 'adx_filter' in tune:
            adx_filter = bool(tune['adx_filter'])

        if 'volume_filter' in tune:
            volume_filter = bool(tune['volume_filter'])

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
    ema_16 = 16
    ma_50 = 50
    ma_100 = 102
    ma_200 = 198
    

    # Optimize: MA, EMA
    if tune:
        if 'ema_16' in tune:
            ema_16 = int(tune['ema_16'])
        if 'ma_50' in tune:
            ma_50 = int(tune['ma_50'])
        if 'ma_100' in tune:
            ma_100 = int(tune['ma_100'])
        if 'ma_200' in tune:
            ma_200 = int(tune['ma_200'])

    ema_16 = indicator.get_EMA(ema_16)
    ma_50 = indicator.get_MA(ma_50)
    ma_100 = indicator.get_MA(ma_100)
    ma_200 = indicator.get_MA(ma_200)



    # ---- MANAGE TRADES ----
    trade_manager = TradeManager(csv_logger, first_balance, monthly_profit_percent_stop_trade, 
                                 tactical_balance, monthly_close_filter, monthly_compound, leverage, safe_leverage_low,
                                 safe_leverage_med, safe_leverage_high)

    # ---- get_ADX ----
    # reuse existing `indicator` instance (created above) to avoid re-initialization
    adx = indicator.get_ADX(
        high_prices,
        low_prices,
        close_prices,
        period=period_adx
    )

    # ---- get_ATR ----
    atr = indicator.get_ATR(high_prices, low_prices, close_prices, period=period_atr)
    # ---- get_ATR_MA ----
    atr_ma = indicator.get_ATR_MA(atr, period=period_atr_ma)
    # ---- get volume average ----
    vol_avg_15_list = indicator.get_volume_avg(volume_prices, period=period_vol_avg)

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
            # bearish cross: EMA crosses below MA
            elif ema_16[i-1] >= ma_50[i-1] and ema_16[i] < ma_50[i]:
                cross_seen = True
                last_cross_dir = 'bear'
                last_cross_index = i
        
        # monthly filter if we got good profit in month, bot will stop on this month
        if monthly_close_filter == True:
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
                balance = liq_updates['balance']
                balance_without_fee = liq_updates['balance_without_fee']
                deducting_fee_total = liq_updates['deducting_fee_total']
                count_closed_orders = liq_updates['count_closed_orders']
                total_losses = liq_updates['total_losses']
                total_long = liq_updates['total_long']
                equity_curve = liq_updates['equity_curve']
                max_drawdown = liq_updates['max_drawdown']
                total_liquids = liq_updates['total_liquids']
                current_position = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if long_close_points is not None:
                    long_close_points.append((i, liq_updates['close_price']))
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
                balance = liq_updates['balance']
                balance_without_fee = liq_updates['balance_without_fee']
                deducting_fee_total = liq_updates['deducting_fee_total']
                count_closed_orders = liq_updates['count_closed_orders']
                total_losses = liq_updates['total_losses']
                total_short = liq_updates['total_short']
                equity_curve = liq_updates['equity_curve']
                max_drawdown = liq_updates['max_drawdown']
                total_liquids = liq_updates['total_liquids']
                current_position = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if short_close_points is not None:
                    short_close_points.append((i, liq_updates['close_price']))
                continue


        # ===================== OPEN LONG =====================
        # Require that EMA/MA50 have crossed and the last cross was bullish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:

                entry_score = 0

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
                # 2) EMA 14 > Ma 50
                if ema_16[i] > ma_50[i]:
                    entry_score += entry_score_ema_vs_ma50
                # 3) close above EMA16
                if close_prices[i] > ema_16[i]:
                    entry_score += entry_score_close_vs_ema16
                # 4) Ma 130 > Ma 200
                if ma_100[i] >= ma_200[i]:
                    entry_score += entry_score_ma_trend
                # 5) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += entry_score_ma_distance_or_candle
                # 6) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] != None and adx[i] >= entry_adx_threshold:
                        entry_score += entry_score_adx
                # 7) ===== VOLUME FILTER =====
                if volume_filter:
                    vol_now = volume_prices[i]
                    vol_avg15 = vol_avg_15_list[i]
                    if vol_now >= volume_spike_multiplier * vol_avg15:
                        entry_score += entry_score_volume
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

                if entry_score >= entry_score_threshold:
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
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

            # update trailing peak
            if highest_since_entry is None:
                highest_since_entry = entry_price
            if high_prices[i] > highest_since_entry:
                highest_since_entry = high_prices[i]

            # 0) loss guard (no leverage): if price drops >= loss_exit_pct from entry
            if entry_price is not None:
                if close_prices[i] <= entry_price * (1 - loss_exit_pct):
                    exit_score += exit_score_loss_guard

            # 1) EMA slope weakness (look back `slope_window` candles)
            if i - slope_window >= 0 and ema_16[i] < ema_16[i - slope_window]:
                exit_score += exit_score_ema_slope

            # 2) EMA crossing below MA50
            if ema_16[i] < ma_50[i]:
                exit_score += exit_score_ema_cross

            # 3) long-term trend weakening (MA100 < MA200)
            if ma_100[i] < ma_200[i]:
                exit_score += exit_score_ma_trend

            # 4) trailing stop based on pullback from peak (armed after min profit)
            if entry_index is not None and i > entry_index:
                if highest_since_entry >= entry_price * (1 + trail_activate_pct):
                    if close_prices[i] <= highest_since_entry * (1 - trail_retrace_pct):
                        exit_score += exit_score_trailing

            # 5) ADX weakening (trend strength fading)
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += exit_score_adx

            # 6) strong opposite candle (body >= ATR * mult)
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] < open_prices[i]:
                    body = open_prices[i] - close_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += exit_score_opposite_candle

            if exit_score >= exit_score_threshold:
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
                
                # count consecutive_losses 
                if profits_lst[-1] < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

                if consecutive_losses >= 2:
                    skip_trades_left = 2
                    consecutive_losses = 0

        # ===================== OPEN SHORT =====================
        # Require that EMA/MA50 have crossed and the last cross was bearish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:
                
                entry_score = 0
                
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
                # 2) EMA 14 < Ma 50
                if ema_16[i] <= ma_50[i]:
                    entry_score += entry_score_ema_vs_ma50
                # 3) close below EMA16
                if close_prices[i] < ema_16[i]:
                    entry_score += entry_score_close_vs_ema16
                # 4) Ma 130 < Ma 200
                if ma_100[i] < ma_200[i]:
                    entry_score += entry_score_ma_trend
                # 5) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += entry_score_ma_distance_or_candle
                # 6) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] != None and adx[i] >= entry_adx_threshold:
                        entry_score += entry_score_adx
                # 7) ===== VOLUME FILTER =====
                if volume_filter:
                    vol_now = volume_prices[i]
                    vol_avg15 = vol_avg_15_list[i]
                    if vol_now >= volume_spike_multiplier * vol_avg15:
                        entry_score += entry_score_volume
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


                if entry_score >= entry_score_threshold:
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
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

            # update trailing trough
            if lowest_since_entry is None:
                lowest_since_entry = entry_price
            if low_prices[i] < lowest_since_entry:
                lowest_since_entry = low_prices[i]

            # 0) loss guard (no leverage): if price rises >= loss_exit_pct from entry
            if entry_price is not None:
                if close_prices[i] >= entry_price * (1 + loss_exit_pct):
                    exit_score += exit_score_loss_guard

            # 1) EMA slope weakness for short (EMA trending up)
            if i - slope_window >= 0 and ema_16[i] > ema_16[i - slope_window]:
                exit_score += exit_score_ema_slope

            # 2) EMA crossing above MA50
            if ema_16[i] > ma_50[i]:
                exit_score += exit_score_ema_cross

            # 3) long-term trend weakening for short (MA100 >= MA200)
            if ma_100[i] >= ma_200[i]:
                exit_score += exit_score_ma_trend

            # 4) trailing stop based on pullback from trough (armed after min profit)
            if entry_index is not None and i > entry_index:
                if lowest_since_entry <= entry_price * (1 - trail_activate_pct):
                    if close_prices[i] >= lowest_since_entry * (1 + trail_retrace_pct):
                        exit_score += exit_score_trailing

            # 5) ADX weakening (trend strength fading)
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += exit_score_adx

            # 6) strong opposite candle (body >= ATR * mult)
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] > open_prices[i]:
                    body = close_prices[i] - open_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += exit_score_opposite_candle

            if exit_score >= exit_score_threshold:
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
                
                # count consecutive_losses 
                if profits_lst[-1] < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

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
    print("count_profit_more_than_8%_monthly:", len(lst_profit_percent_per_month))

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
    minutes=minutes
    )

    # optimize already determined earlier; skip plotting when optimizing
    # Draw diagram with OHLC candles (Open/High/Low/Close)
    if optimize is False:
            ypoints_total_balance = [row[1] for row in chart_data]
            total_candles = len(close_prices)
            if total_candles == 0:
                return {
                    'final_balance': balance,
                    'total_profit': round(sum(profits_lst), 6),
                    'total_profit_percent': round(t_profit_percent, 6),
                    'closed_trades': count_closed_orders,
                    'wins': total_wins,
                    'losses': total_losses,
                    'maximum_drawdown': round(max_drawdown, 2),
                    "profit_more_than_8%": len(lst_profit_percent_per_month)
                }

            nav_offset = max(0, int(plot_end_offset))

            chart_palette = {
                "bg": "#070B12",
                "panel_bg": "#101722",
                "grid": "#2A3443",
                "text": "#DCE4F0",
                "muted": "#A7B4C8",
                "up": "#4CD47A",
                "down": "#FF6B7A",
                "ema16": "#66C7FF",
                "ma50": "#66C7FF",
                "ma100": "#FFC774",
                "ma200": "#FFC774",
                "mark": "#5FA2D9",
                "long_open": "#7FE0B0",
                "long_close": "#2FCF82",
                "short_open": "#FF98A8",
                "short_close": "#E96A7E",
                "equity": "#5CC8F2",
                "divider": "#44586E",
                "crosshair": "#9AABC1",
                "label_fg": "#0C1420",
                "label_bg": "#D7E0EC",
                "label_edge": "#8EA2B8",
            }
            dark_mc = mpf.make_marketcolors(
                up=chart_palette["up"],
                down=chart_palette["down"],
                edge="inherit",
                wick="inherit",
                volume="inherit",
            )
            chart_style = mpf.make_mpf_style(
                base_mpf_style="nightclouds",
                marketcolors=dark_mc,
                y_on_right=False,
                facecolor=chart_palette["panel_bg"],
                figcolor=chart_palette["bg"],
                gridcolor=chart_palette["grid"],
                gridstyle="-.",
                rc={
                    "axes.facecolor": chart_palette["panel_bg"],
                    "axes.labelcolor": chart_palette["text"],
                    "xtick.color": chart_palette["muted"],
                    "ytick.color": chart_palette["muted"],
                    "text.color": chart_palette["text"],
                    "axes.edgecolor": chart_palette["divider"],
                },
            )

            if plot_max_candles > 0:
                window_size_base = min(int(plot_max_candles), total_candles)
            else:
                window_size_base = total_candles
            window_size_base = max(1, window_size_base)
            step_candles = max(1, int(plot_step_candles))

            fig = plt.figure(figsize=(14.5, 8.2), facecolor=chart_palette["bg"])
            grid = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.04)
            ax_price = fig.add_subplot(grid[0])
            ax_equity = fig.add_subplot(grid[1], sharex=ax_price)

            def set_figure_fullscreen():
                """Resize to a near-fullscreen window without forcing true fullscreen."""
                try:
                    manager = getattr(fig.canvas, "manager", None)
                    if manager is None:
                        return

                    window = getattr(manager, "window", None)
                    width_ratio = float(np.clip(plot_window_width_scale, 0.50, 1.0))
                    height_ratio = float(np.clip(plot_window_height_scale, 0.50, 1.0))

                    # TkAgg
                    if (
                        window is not None
                        and hasattr(window, "winfo_screenwidth")
                        and hasattr(window, "winfo_screenheight")
                        and hasattr(window, "geometry")
                    ):
                        screen_w = int(window.winfo_screenwidth())
                        screen_h = int(window.winfo_screenheight())
                        target_w = max(900, min(screen_w, int(screen_w * width_ratio)))
                        target_h = max(620, min(screen_h, int(screen_h * height_ratio)))
                        x_pos = max(0, (screen_w - target_w) // 2)
                        y_pos = max(0, (screen_h - target_h) // 2)
                        if hasattr(window, "state"):
                            try:
                                window.state("normal")
                            except Exception:
                                pass
                        window.geometry(f"{target_w}x{target_h}+{x_pos}+{y_pos}")
                        return

                    # Qt backends
                    if window is not None and hasattr(window, "screen") and hasattr(window, "setGeometry"):
                        try:
                            screen_obj = window.screen()
                            available = screen_obj.availableGeometry() if screen_obj is not None else None
                            if available is not None:
                                avail_w = int(available.width())
                                avail_h = int(available.height())
                                target_w = max(900, min(avail_w, int(avail_w * width_ratio)))
                                target_h = max(620, min(avail_h, int(avail_h * height_ratio)))
                                x_pos = int(available.x() + ((avail_w - target_w) / 2))
                                y_pos = int(available.y() + ((avail_h - target_h) / 2))
                                if hasattr(window, "showNormal"):
                                    window.showNormal()
                                window.setGeometry(x_pos, y_pos, target_w, target_h)
                                return
                        except Exception:
                            pass
                        if hasattr(window, "showMaximized"):
                            try:
                                window.showMaximized()
                                return
                            except Exception:
                                pass

                    # Generic fallback
                    resize = getattr(manager, "resize", None)
                    if callable(resize):
                        dpi = float(fig.dpi) if fig.dpi else 100.0
                        base_w = int(fig.get_figwidth() * dpi)
                        base_h = int(fig.get_figheight() * dpi)
                        resize(max(900, base_w), max(620, base_h))
                except Exception:
                    pass

            nav_state = {
                "window_size": window_size_base,
                "offset": min(max(0, int(nav_offset)), max(0, total_candles - window_size_base)),
                "max_offset": max(0, total_candles - window_size_base),
                "press_px": None,
                "press_axis_id": None,
                "drag_mode": None,  # None | "nav" | "yscale"
                "did_live_drag": False,
                "last_drag_update_ts": 0.0,
                "drag_update_interval_s": max(0.005, float(plot_drag_update_interval_ms) / 1000.0),
                "preview_mode": False,
                "initial_xlim": None,
                "initial_xlim_by_axis": {},
                "fixed_ylim_price": None,
                "fixed_ylim_equity": None,
                "yscale_press_y_px": None,
                "yscale_start_ylim": None,
                "vline_price": None,
                "vline_equity": None,
                "hline_price": None,
                "hline_equity": None,
                "price_label": None,
                "balance_label": None,
                "rendering": False,
            }

            def has_finite(series_obj):
                vals = series_obj.to_numpy(dtype=float)
                return np.isfinite(vals).any()

            def downsample_ohlc(open_arr, high_arr, low_arr, close_arr, time_arr, step):
                if step <= 1:
                    return open_arr, high_arr, low_arr, close_arr, time_arr
                n = len(close_arr)
                o_out, h_out, l_out, c_out, t_out = [], [], [], [], []
                for s in range(0, n, step):
                    e = min(s + step, n)
                    seg_h = high_arr[s:e]
                    seg_l = low_arr[s:e]
                    o_out.append(open_arr[s])
                    h_out.append(np.nanmax(seg_h) if np.isfinite(seg_h).any() else np.nan)
                    l_out.append(np.nanmin(seg_l) if np.isfinite(seg_l).any() else np.nan)
                    c_out.append(close_arr[e - 1])
                    t_out.append(time_arr[e - 1])
                return (
                    np.asarray(o_out, dtype=float),
                    np.asarray(h_out, dtype=float),
                    np.asarray(l_out, dtype=float),
                    np.asarray(c_out, dtype=float),
                    np.asarray(t_out, dtype=object),
                )

            def downsample_last(arr, step):
                if step <= 1:
                    return np.asarray(arr, dtype=float)
                n = len(arr)
                out = [arr[min(s + step, n) - 1] for s in range(0, n, step)]
                return np.asarray(out, dtype=float)

            def downsample_last_valid(arr, step):
                if step <= 1:
                    return np.asarray(arr, dtype=float)
                n = len(arr)
                out = []
                for s in range(0, n, step):
                    e = min(s + step, n)
                    seg = arr[s:e]
                    valid = seg[np.isfinite(seg)]
                    out.append(valid[-1] if valid.size > 0 else np.nan)
                return np.asarray(out, dtype=float)

            def valid_ylim(ylim_vals):
                if ylim_vals is None:
                    return False
                try:
                    y0, y1 = float(ylim_vals[0]), float(ylim_vals[1])
                except Exception:
                    return False
                return np.isfinite([y0, y1]).all() and (y1 != y0)

            def set_fixed_ylim_for_axis(axis_obj, ylim_vals):
                if axis_obj is None or not valid_ylim(ylim_vals):
                    return
                y0, y1 = float(ylim_vals[0]), float(ylim_vals[1])
                if id(axis_obj) == id(ax_price):
                    nav_state["fixed_ylim_price"] = (y0, y1)
                elif id(axis_obj) == id(ax_equity):
                    nav_state["fixed_ylim_equity"] = (y0, y1)

            def get_axis_by_id(axis_id):
                for axis_obj in fig.axes:
                    if id(axis_obj) == axis_id:
                        return axis_obj
                return None

            def render_current():
                if nav_state["rendering"]:
                    return
                nav_state["rendering"] = True
                try:
                    window_size = int(nav_state["window_size"])
                    window_size = min(max(1, window_size), total_candles)
                    nav_state["window_size"] = window_size
                    window_size = max(1, window_size)

                    max_offset = max(0, total_candles - window_size)
                    offset_clamped = min(max(int(nav_state["offset"]), 0), max_offset)
                    nav_state["offset"] = offset_clamped
                    nav_state["max_offset"] = max_offset

                    plot_end = total_candles - offset_clamped
                    plot_start = max(0, plot_end - window_size)
                    if plot_end <= plot_start:
                        return

                    full_open = np.asarray(open_prices[plot_start:plot_end], dtype=float)
                    full_high = np.asarray(high_prices[plot_start:plot_end], dtype=float)
                    full_low = np.asarray(low_prices[plot_start:plot_end], dtype=float)
                    full_close = np.asarray(close_prices[plot_start:plot_end], dtype=float)
                    full_close_times = np.asarray(close_times[plot_start:plot_end], dtype=object)
                    full_ema16 = np.asarray(ema_16[plot_start:plot_end], dtype=float)
                    full_ma50 = np.asarray(ma_50[plot_start:plot_end], dtype=float)
                    full_ma100 = np.asarray(ma_100[plot_start:plot_end], dtype=float)
                    full_ma200 = np.asarray(ma_200[plot_start:plot_end], dtype=float)
                    full_equity = np.asarray(ypoints_total_balance[plot_start:plot_end], dtype=float)
                    n_full = len(full_close)
                    if n_full == 0:
                        return

                    time_index_full = pd.to_datetime(full_close_times, utc=True)

                    # mark 13:30 UTC close points (use close_times)
                    mark_arr = np.full(n_full, np.nan, dtype=float)
                    mark_mask = (time_index_full.hour == 13) & (time_index_full.minute == 30)
                    mark_arr[mark_mask] = full_close[mark_mask]

                    long_open_arr = np.full(n_full, np.nan, dtype=float)
                    long_close_arr = np.full(n_full, np.nan, dtype=float)
                    short_open_arr = np.full(n_full, np.nan, dtype=float)
                    short_close_arr = np.full(n_full, np.nan, dtype=float)

                    def place_trade_markers(points, arr):
                        if not points:
                            return
                        for idx, price in points:
                            local_idx = idx - plot_start
                            if 0 <= local_idx < len(arr) and idx < plot_end:
                                arr[local_idx] = price

                    place_trade_markers(long_open_points, long_open_arr)
                    place_trade_markers(long_close_points, long_close_arr)
                    place_trade_markers(short_open_points, short_open_arr)
                    place_trade_markers(short_close_points, short_close_arr)

                    # Adaptive render density:
                    # - Zoom in  => full detail (no downsample)
                    # - Zoom out => render fewer candles for smoother performance
                    max_render = int(plot_max_render_candles)
                    if nav_state.get("preview_mode"):
                        preview_factor = float(np.clip(plot_drag_preview_factor, 0.15, 1.0))
                        max_render = max(180, int(max_render * preview_factor))
                    if n_full <= max_render:
                        target_render = n_full
                    elif n_full <= (max_render * 3):
                        # medium zoom-out: keep more detail
                        target_render = min(max_render, max(200, int(n_full * 0.5)))
                    else:
                        # far zoom-out (including full-history): prioritize smooth rendering
                        target_render = min(max_render, max(200, int(n_full * 0.33)))
                    render_step = max(1, int(np.ceil(n_full / max(1, target_render))))

                    ds_open, ds_high, ds_low, ds_close, ds_times = downsample_ohlc(
                        full_open, full_high, full_low, full_close, full_close_times, render_step
                    )
                    ds_ema16 = downsample_last(full_ema16, render_step)
                    ds_ma50 = downsample_last(full_ma50, render_step)
                    ds_ma100 = downsample_last(full_ma100, render_step)
                    ds_ma200 = downsample_last(full_ma200, render_step)
                    ds_equity = downsample_last(full_equity, render_step)
                    ds_mark = downsample_last_valid(mark_arr, render_step)
                    ds_long_open = downsample_last_valid(long_open_arr, render_step)
                    ds_long_close = downsample_last_valid(long_close_arr, render_step)
                    ds_short_open = downsample_last_valid(short_open_arr, render_step)
                    ds_short_close = downsample_last_valid(short_close_arr, render_step)

                    time_index = pd.to_datetime(ds_times, utc=True)
                    price_df = pd.DataFrame(
                        {
                            "Open": ds_open,
                            "High": ds_high,
                            "Low": ds_low,
                            "Close": ds_close,
                        },
                        index=time_index,
                    )
                    if price_df.empty:
                        return

                    ema16_series = pd.Series(ds_ema16, index=time_index)
                    ma50_series = pd.Series(ds_ma50, index=time_index)
                    ma100_series = pd.Series(ds_ma100, index=time_index)
                    ma200_series = pd.Series(ds_ma200, index=time_index)
                    equity_series = pd.Series(ds_equity, index=time_index)
                    mark_series = pd.Series(ds_mark, index=time_index)
                    long_open_series = pd.Series(ds_long_open, index=time_index)
                    long_close_series = pd.Series(ds_long_close, index=time_index)
                    short_open_series = pd.Series(ds_short_open, index=time_index)
                    short_close_series = pd.Series(ds_short_close, index=time_index)

                    ax_price.cla()
                    ax_equity.cla()

                    preview_mode = bool(nav_state.get("preview_mode"))
                    add_plots = []
                    if has_finite(ema16_series):
                        add_plots.append(
                            mpf.make_addplot(ema16_series, ax=ax_price, color=chart_palette["ema16"], width=1.0)
                        )
                    if has_finite(ma50_series):
                        add_plots.append(
                            mpf.make_addplot(
                                ma50_series,
                                ax=ax_price,
                                color=chart_palette["ma50"],
                                width=1.0,
                                linestyle="--",
                            )
                        )
                    if has_finite(ma100_series):
                        add_plots.append(
                            mpf.make_addplot(ma100_series, ax=ax_price, color=chart_palette["ma100"], width=1.0)
                        )
                    if has_finite(ma200_series):
                        add_plots.append(
                            mpf.make_addplot(
                                ma200_series,
                                ax=ax_price,
                                color=chart_palette["ma200"],
                                width=1.0,
                                linestyle="--",
                            )
                        )
                    if (not preview_mode) and has_finite(mark_series):
                        add_plots.append(
                            mpf.make_addplot(
                                mark_series,
                                ax=ax_price,
                                type="scatter",
                                marker="o",
                                markersize=46,
                                color=chart_palette["mark"],
                                alpha=0.9,
                            )
                        )
                    if (not preview_mode) and has_finite(long_open_series):
                        add_plots.append(
                            mpf.make_addplot(
                                long_open_series,
                                ax=ax_price,
                                type="scatter",
                                marker="s",
                                markersize=46,
                                color=chart_palette["long_open"],
                                alpha=0.9,
                            )
                        )
                    if (not preview_mode) and has_finite(long_close_series):
                        add_plots.append(
                            mpf.make_addplot(
                                long_close_series,
                                ax=ax_price,
                                type="scatter",
                                marker="D",
                                markersize=46,
                                color=chart_palette["long_close"],
                                alpha=0.9,
                            )
                        )
                    if (not preview_mode) and has_finite(short_open_series):
                        add_plots.append(
                            mpf.make_addplot(
                                short_open_series,
                                ax=ax_price,
                                type="scatter",
                                marker="s",
                                markersize=46,
                                color=chart_palette["short_open"],
                                alpha=0.9,
                            )
                        )
                    if (not preview_mode) and has_finite(short_close_series):
                        add_plots.append(
                            mpf.make_addplot(
                                short_close_series,
                                ax=ax_price,
                                type="scatter",
                                marker="D",
                                markersize=46,
                                color=chart_palette["short_close"],
                                alpha=0.9,
                            )
                        )
                    if has_finite(equity_series):
                        add_plots.append(
                            mpf.make_addplot(equity_series, ax=ax_equity, color=chart_palette["equity"], width=1.2)
                        )

                    last_close_price = float(ds_close[-1])
                    plot_kwargs = {}
                    if len(time_index) > 1:
                        plot_kwargs["xlim"] = (time_index[0], time_index[-1])

                    mpf.plot(
                        price_df,
                        type="candle",
                        style=chart_style,
                        ax=ax_price,
                        addplot=add_plots if add_plots else None,
                        datetime_format="%Y-%m-%d %H:%M",
                        xrotation=15,
                        tight_layout=False,
                        warn_too_much_data=int(len(price_df) + 10),
                        **plot_kwargs,
                    )

                    ax_price.set_facecolor(chart_palette["panel_bg"])
                    ax_equity.set_facecolor(chart_palette["panel_bg"])
                    ax_price.yaxis.label.set_color(chart_palette["text"])
                    ax_equity.yaxis.label.set_color(chart_palette["text"])
                    ax_price.tick_params(axis="x", colors=chart_palette["muted"])
                    ax_price.tick_params(axis="y", colors=chart_palette["muted"])
                    ax_equity.tick_params(axis="x", colors=chart_palette["muted"])
                    ax_equity.tick_params(axis="y", colors=chart_palette["muted"])
                    ax_price.set_axisbelow(True)
                    ax_equity.set_axisbelow(True)
                    ax_price.grid(
                        True,
                        which="major",
                        axis="both",
                        linestyle="--",
                        linewidth=0.55,
                        color=chart_palette["grid"],
                        alpha=0.30,
                    )
                    ax_equity.grid(
                        True,
                        which="major",
                        axis="both",
                        linestyle="--",
                        linewidth=0.55,
                        color=chart_palette["grid"],
                        alpha=0.30,
                    )

                    fixed_price_ylim = nav_state.get("fixed_ylim_price")
                    if valid_ylim(fixed_price_ylim):
                        ax_price.set_ylim(fixed_price_ylim)
                    fixed_equity_ylim = nav_state.get("fixed_ylim_equity")
                    if valid_ylim(fixed_equity_ylim):
                        ax_equity.set_ylim(fixed_equity_ylim)

                    ax_price.set_title(
                        f"BTC - OHLC + MAs | Last: ${last_close_price:,.2f} | Candles: {len(price_df)} (x{render_step}) | Offset: {offset_clamped} | Drag/Wheel/\u2190/\u2192 | \u2191 oldest | \u2193 latest",
                        color=chart_palette["text"],
                    )
                    ax_price.set_ylabel("BTC Price")
                    ax_equity.set_ylabel("Balance ($)")
                    ax_price.tick_params(labelbottom=False)

                    # visual separator between price panel and equity panel
                    ax_price.spines["bottom"].set_visible(True)
                    ax_price.spines["bottom"].set_color(chart_palette["divider"])
                    ax_price.spines["bottom"].set_linewidth(1.4)
                    ax_equity.spines["top"].set_visible(True)
                    ax_equity.spines["top"].set_color(chart_palette["divider"])
                    ax_equity.spines["top"].set_linewidth(1.4)

                    # Crosshair (TradingView-like): vertical + horizontal + end labels on both panels.
                    x_left, x_right = ax_price.get_xlim()
                    y_bottom, y_top = ax_price.get_ylim()
                    x_mid = (x_left + x_right) / 2.0
                    y_mid = (y_bottom + y_top) / 2.0
                    y_eq_bottom, y_eq_top = ax_equity.get_ylim()
                    y_eq_mid = (y_eq_bottom + y_eq_top) / 2.0
                    cross_color = chart_palette["crosshair"]
                    nav_state["vline_price"] = ax_price.axvline(
                        x_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.9, visible=False, zorder=30
                    )
                    nav_state["vline_equity"] = ax_equity.axvline(
                        x_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.75, visible=False, zorder=30
                    )
                    nav_state["hline_price"] = ax_price.axhline(
                        y_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.9, visible=False, zorder=30
                    )
                    nav_state["hline_equity"] = ax_equity.axhline(
                        y_eq_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.85, visible=False, zorder=30
                    )
                    label_transform = mtransforms.blended_transform_factory(ax_price.transAxes, ax_price.transData)
                    nav_state["price_label"] = ax_price.text(
                        0.002,
                        y_mid,
                        "",
                        transform=label_transform,
                        ha="left",
                        va="center",
                        fontsize=8,
                        color=chart_palette["label_fg"],
                        bbox=dict(
                            boxstyle="round,pad=0.18",
                            facecolor=chart_palette["label_bg"],
                            edgecolor=chart_palette["label_edge"],
                            linewidth=0.8,
                        ),
                        visible=False,
                        zorder=31,
                    )
                    balance_transform = mtransforms.blended_transform_factory(ax_equity.transAxes, ax_equity.transData)
                    nav_state["balance_label"] = ax_equity.text(
                        0.002,
                        y_eq_mid,
                        "",
                        transform=balance_transform,
                        ha="left",
                        va="center",
                        fontsize=8,
                        color=chart_palette["label_fg"],
                        bbox=dict(
                            boxstyle="round,pad=0.18",
                            facecolor=chart_palette["label_bg"],
                            edgecolor=chart_palette["label_edge"],
                            linewidth=0.8,
                        ),
                        visible=False,
                        zorder=31,
                    )

                    fig.subplots_adjust(left=0.06, right=0.99, top=0.92, bottom=0.09, hspace=0.04)
                    nav_state["initial_xlim"] = ax_price.get_xlim()
                    nav_state["initial_xlim_by_axis"] = {id(ax): ax.get_xlim() for ax in fig.axes}
                    fig.canvas.draw_idle()
                finally:
                    nav_state["rendering"] = False

            def request_nav(cmd, shift_candles=None):
                if shift_candles is None:
                    shift_candles = max(1, min(int(step_candles), int(nav_state["window_size"])))
                shift_candles = max(1, int(shift_candles))
                if cmd == "older":
                    nav_state["offset"] = min(nav_state["max_offset"], nav_state["offset"] + shift_candles)
                    render_current()
                elif cmd == "newer":
                    nav_state["offset"] = max(0, nav_state["offset"] - shift_candles)
                    render_current()

            def hide_crosshair(redraw=False):
                changed = False
                for key in ("vline_price", "vline_equity", "hline_price", "hline_equity", "price_label", "balance_label"):
                    artist = nav_state.get(key)
                    if artist is not None and artist.get_visible():
                        artist.set_visible(False)
                        changed = True
                if redraw and changed:
                    fig.canvas.draw_idle()

            def get_toolbar_mode():
                toolbar = getattr(getattr(fig.canvas, "manager", None), "toolbar", None)
                mode = str(getattr(toolbar, "mode", "")).lower() if toolbar is not None else ""
                return mode

            def sync_from_axis_xlim(active_ax):
                initial_map = nav_state.get("initial_xlim_by_axis", {})
                initial_xlim = initial_map.get(id(active_ax), nav_state.get("initial_xlim"))
                if initial_xlim is None:
                    return False

                cur_left, cur_right = active_ax.get_xlim()
                init_left, init_right = initial_xlim
                if not np.isfinite([cur_left, cur_right, init_left, init_right]).all():
                    return False

                init_min, init_max = (min(init_left, init_right), max(init_left, init_right))
                cur_min, cur_max = (min(cur_left, cur_right), max(cur_left, cur_right))
                init_span = init_max - init_min
                cur_span = cur_max - cur_min
                if init_span <= 0 or cur_span <= 0:
                    return False

                old_size = int(nav_state["window_size"])
                old_size = max(1, min(total_candles, old_size))
                old_offset = min(max(int(nav_state["offset"]), 0), max(0, total_candles - old_size))
                old_start = total_candles - old_offset - old_size

                # Map the exact visible x-range on toolbar interaction to data indices.
                left_frac = (cur_min - init_min) / init_span
                right_frac = (cur_max - init_min) / init_span

                raw_start = old_start + (left_frac * old_size)
                raw_end = old_start + (right_frac * old_size)

                new_start = int(np.floor(raw_start))
                new_end = int(np.ceil(raw_end))

                min_size = max(1, int(plot_min_zoom_candles))
                if (new_end - new_start) < min_size:
                    center = (raw_start + raw_end) / 2.0
                    new_start = int(round(center - (min_size / 2.0)))
                    new_end = new_start + min_size

                if new_start < 0:
                    new_end -= new_start
                    new_start = 0
                if new_end > total_candles:
                    new_start -= (new_end - total_candles)
                    new_end = total_candles

                new_start = max(0, min(total_candles - 1, new_start))
                new_end = max(new_start + 1, min(total_candles, new_end))
                new_size = max(1, min(total_candles, new_end - new_start))
                new_offset = total_candles - (new_start + new_size)
                new_offset = max(0, min(max(0, total_candles - new_size), new_offset))

                changed = (new_size != old_size) or (new_offset != old_offset)
                if changed:
                    nav_state["window_size"] = new_size
                    nav_state["offset"] = new_offset
                    render_current()
                    return True
                return False

            def on_key(event):
                key = (event.key or "").lower()
                if key in ("left", "a"):
                    request_nav("older")
                elif key in ("right", "d"):
                    request_nav("newer")
                elif key in ("up", "w", "pageup"):
                    nav_state["offset"] = nav_state["max_offset"]
                    render_current()
                elif key in ("down", "s", "pagedown"):
                    nav_state["offset"] = 0
                    render_current()
                elif key in ("0", "home"):
                    # quick full-history view
                    nav_state["window_size"] = total_candles
                    nav_state["offset"] = 0
                    render_current()
                elif key in ("1", "end"):
                    # quick return to default recent window
                    nav_state["window_size"] = window_size_base
                    nav_state["offset"] = 0
                    render_current()

            def on_move(event):
                if nav_state["rendering"]:
                    return

                drag_mode = nav_state.get("drag_mode")
                toolbar_mode = get_toolbar_mode()

                # Right-drag vertical scaling (persistent y-range).
                if drag_mode == "yscale":
                    active_axis = get_axis_by_id(nav_state.get("press_axis_id"))
                    if active_axis is None or event.y is None:
                        return
                    start_y = nav_state.get("yscale_press_y_px")
                    start_ylim = nav_state.get("yscale_start_ylim")
                    if start_y is None or not valid_ylim(start_ylim):
                        return

                    dy = float(event.y) - float(start_y)
                    base_y0, base_y1 = float(start_ylim[0]), float(start_ylim[1])
                    center_y = (base_y0 + base_y1) / 2.0
                    base_span = abs(base_y1 - base_y0)
                    sensitivity = max(0.0002, float(plot_yscale_drag_sensitivity))
                    scale = float(np.exp(-dy * sensitivity))
                    scale = float(np.clip(scale, 0.08, 12.0))
                    new_span = max(1e-9, base_span * scale)
                    new_ylim = (center_y - (new_span / 2.0), center_y + (new_span / 2.0))
                    active_axis.set_ylim(new_ylim)
                    set_fixed_ylim_for_axis(active_axis, new_ylim)
                    fig.canvas.draw_idle()
                    return

                # Left-drag horizontal navigation with live updates.
                # Keep this active for normal mode and toolbar pan mode; skip only zoom-rect mode.
                if drag_mode == "nav" and ("zoom" not in toolbar_mode):
                    if event.x is None:
                        return
                    active_axis = get_axis_by_id(nav_state.get("press_axis_id"))
                    if active_axis is None:
                        active_axis = event.inaxes if (event.inaxes in fig.axes) else ax_price

                    axis_width = float(active_axis.bbox.width) if active_axis is not None else 0.0
                    press_px = nav_state.get("press_px")
                    if axis_width <= 0 or press_px is None:
                        return

                    delta_px = float(event.x) - float(press_px)
                    drag_threshold_px = max(1.2, axis_width * 0.0018)
                    now_ts = time.perf_counter()
                    if (
                        abs(delta_px) >= drag_threshold_px
                        and (now_ts - float(nav_state.get("last_drag_update_ts", 0.0))) >= float(nav_state["drag_update_interval_s"])
                    ):
                        move_ratio = min(1.0, abs(delta_px) / axis_width)
                        shift = max(1, int(round(move_ratio * int(nav_state["window_size"]))))
                        nav_state["preview_mode"] = True
                        nav_state["did_live_drag"] = True
                        nav_state["last_drag_update_ts"] = now_ts
                        request_nav("older" if delta_px > 0 else "newer", shift_candles=shift)
                        nav_state["press_px"] = float(event.x)
                    return

                if event.x is None or event.y is None:
                    hide_crosshair(redraw=True)
                    return
                if event.inaxes is None or event.inaxes not in fig.axes:
                    hide_crosshair(redraw=True)
                    return

                vline_price = nav_state.get("vline_price")
                vline_equity = nav_state.get("vline_equity")
                hline_price = nav_state.get("hline_price")
                hline_equity = nav_state.get("hline_equity")
                price_label = nav_state.get("price_label")
                balance_label = nav_state.get("balance_label")
                if None in (vline_price, vline_equity, hline_price, hline_equity, price_label, balance_label):
                    return

                cursor_x = ax_price.transData.inverted().transform((event.x, event.y))[0]
                cursor_y_on_price = ax_price.transData.inverted().transform((event.x, event.y))[1]
                cursor_y_on_equity = ax_equity.transData.inverted().transform((event.x, event.y))[1]

                vline_price.set_xdata([cursor_x, cursor_x])
                vline_equity.set_xdata([cursor_x, cursor_x])
                vline_price.set_visible(True)
                vline_equity.set_visible(True)

                # show price horizontal/label only when cursor is inside price panel
                if ax_price.bbox.contains(event.x, event.y):
                    hline_price.set_ydata([cursor_y_on_price, cursor_y_on_price])
                    hline_price.set_visible(True)
                    price_label.set_y(cursor_y_on_price)
                    price_label.set_text(f"{cursor_y_on_price:,.2f}")
                    price_label.set_visible(True)
                else:
                    hline_price.set_visible(False)
                    price_label.set_visible(False)

                # show balance horizontal/label only when cursor is inside equity panel
                if ax_equity.bbox.contains(event.x, event.y):
                    hline_equity.set_ydata([cursor_y_on_equity, cursor_y_on_equity])
                    hline_equity.set_visible(True)
                    balance_label.set_y(cursor_y_on_equity)
                    balance_label.set_text(f"${cursor_y_on_equity:,.2f}")
                    balance_label.set_visible(True)
                else:
                    hline_equity.set_visible(False)
                    balance_label.set_visible(False)

                fig.canvas.draw_idle()

            def on_leave(_event):
                hide_crosshair(redraw=True)

            def on_press(event):
                if event.inaxes is None:
                    return
                if event.inaxes not in fig.axes:
                    return
                if event.x is None or event.y is None:
                    return

                button = getattr(event, "button", None)
                button_text = str(button).lower()
                is_right_click = (button == 3) or ("right" in button_text)

                nav_state["press_axis_id"] = id(event.inaxes)
                if is_right_click:
                    nav_state["drag_mode"] = "yscale"
                    nav_state["yscale_press_y_px"] = float(event.y)
                    nav_state["yscale_start_ylim"] = event.inaxes.get_ylim()
                    nav_state["press_px"] = None
                    nav_state["did_live_drag"] = False
                    return

                nav_state["drag_mode"] = "nav"
                nav_state["press_px"] = float(event.x)
                nav_state["yscale_press_y_px"] = None
                nav_state["yscale_start_ylim"] = None
                nav_state["did_live_drag"] = False
                nav_state["last_drag_update_ts"] = 0.0

            def on_release(event):
                if nav_state["rendering"]:
                    return

                active_ax = event.inaxes if (event.inaxes in fig.axes) else get_axis_by_id(nav_state.get("press_axis_id"))
                if active_ax is None:
                    active_ax = ax_price
                toolbar_mode = get_toolbar_mode()
                drag_mode = nav_state.get("drag_mode")

                if drag_mode == "yscale":
                    nav_state["drag_mode"] = None
                    nav_state["press_axis_id"] = None
                    nav_state["yscale_press_y_px"] = None
                    nav_state["yscale_start_ylim"] = None
                    return

                if drag_mode == "nav" and nav_state.get("did_live_drag"):
                    nav_state["press_px"] = None
                    nav_state["press_axis_id"] = None
                    nav_state["drag_mode"] = None
                    nav_state["preview_mode"] = False
                    nav_state["did_live_drag"] = False
                    render_current()
                    return

                # If toolbar pan/zoom tools are active and we did not handle live-drag ourselves, sync from x-limits.
                if ("pan" in toolbar_mode) or ("zoom" in toolbar_mode):
                    set_fixed_ylim_for_axis(ax_price, ax_price.get_ylim())
                    set_fixed_ylim_for_axis(ax_equity, ax_equity.get_ylim())
                    nav_state["press_px"] = None
                    nav_state["press_axis_id"] = None
                    nav_state["drag_mode"] = None
                    nav_state["preview_mode"] = False
                    nav_state["did_live_drag"] = False
                    sync_from_axis_xlim(active_ax)
                    return

                # direct drag gesture in pixels
                press_px = nav_state.get("press_px")
                release_px = float(event.x) if event.x is not None else None
                if press_px is not None and release_px is not None:
                    axis = active_ax
                    axis_width = float(axis.bbox.width) if axis is not None else 0.0
                    if axis_width > 0:
                        delta_px = release_px - press_px
                        drag_threshold_px = max(8.0, axis_width * 0.01)
                        if abs(delta_px) > drag_threshold_px:
                            move_ratio = min(1.0, abs(delta_px) / axis_width)
                            shift = max(1, int(round(move_ratio * int(nav_state["window_size"]))))
                            nav_state["press_px"] = None
                            nav_state["press_axis_id"] = None
                            nav_state["drag_mode"] = None
                            nav_state["preview_mode"] = False
                            nav_state["did_live_drag"] = False
                            request_nav("older" if delta_px > 0 else "newer", shift_candles=shift)
                            return

                nav_state["press_px"] = None
                nav_state["press_axis_id"] = None
                nav_state["drag_mode"] = None
                nav_state["preview_mode"] = False
                nav_state["did_live_drag"] = False

                # fallback: if x-limits changed for any reason, sync
                sync_from_axis_xlim(active_ax)

            def on_scroll(event):
                if event.inaxes is None:
                    return
                if event.inaxes not in fig.axes:
                    return
                if nav_state["rendering"]:
                    return

                active_ax = event.inaxes
                current_size = int(nav_state["window_size"])
                step = getattr(event, "step", 0)
                button = str(getattr(event, "button", "")).lower()
                if step > 0 or button == "up":
                    new_size = max(int(plot_min_zoom_candles), int(round(current_size * float(plot_zoom_in_factor))))
                elif step < 0 or button == "down":
                    new_size = min(total_candles, int(round(current_size * float(plot_zoom_out_factor))))
                else:
                    return

                new_size = max(1, min(total_candles, new_size))
                if new_size == current_size:
                    return

                old_size = current_size
                old_offset = min(max(int(nav_state["offset"]), 0), max(0, total_candles - old_size))
                old_start = total_candles - old_offset - old_size

                # Cursor-centered zoom: keep the candle under mouse anchored.
                focus = 0.5
                try:
                    if event.x is not None and event.y is not None:
                        x_left, x_right = active_ax.get_xlim()
                        x_span = x_right - x_left
                        if x_span != 0:
                            cursor_x = float(active_ax.transData.inverted().transform((event.x, event.y))[0])
                            focus = float(np.clip((cursor_x - x_left) / x_span, 0.0, 1.0))
                except Exception:
                    focus = 0.5

                anchor_index = old_start + (focus * old_size)
                new_start = int(round(anchor_index - (focus * new_size)))
                new_start = max(0, min(total_candles - new_size, new_start))
                new_offset = total_candles - (new_start + new_size)

                nav_state["window_size"] = new_size
                nav_state["offset"] = new_offset
                render_current()

            cid_key = fig.canvas.mpl_connect("key_press_event", on_key)
            cid_press = fig.canvas.mpl_connect("button_press_event", on_press)
            cid_release = fig.canvas.mpl_connect("button_release_event", on_release)
            cid_scroll = fig.canvas.mpl_connect("scroll_event", on_scroll)
            cid_move = fig.canvas.mpl_connect("motion_notify_event", on_move)
            cid_leave = fig.canvas.mpl_connect("figure_leave_event", on_leave)

            set_figure_fullscreen()
            render_current()
            plt.show()

            fig.canvas.mpl_disconnect(cid_key)
            fig.canvas.mpl_disconnect(cid_press)
            fig.canvas.mpl_disconnect(cid_release)
            fig.canvas.mpl_disconnect(cid_scroll)
            fig.canvas.mpl_disconnect(cid_move)
            fig.canvas.mpl_disconnect(cid_leave)

    # generate monthly summary CSV silently (no terminal output)
    if not optimize:
        try:
            write_monthly_summary(in_file='data_orders.csv', out_file='monthly_data_orders.csv', quiet=True)
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
        "profit_more_than_8%": len(lst_profit_percent_per_month)
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
