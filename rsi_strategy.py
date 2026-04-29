# NOTE: Strategy executes With candle Open prices, High prices, Low prices, Close prices

import pandas as pd
import numpy as np
import os
import json

# My Codes :
from trade_csv_logger import TradeCSVLogger
from indicators import Indicator
from get_candle_index import get_candle_index, get_month_start_indices
from trademanager import TradeManager
from check_monthly_data import write_monthly_summary
from chart_renderer import render_backtest_chart
from fetch_calculate_data import fetch_all_data, trade_duration


# start = get_candle_index("2025-01-01")   ----> 244944
# end = get_candle_index("2026-02-23")     ----> 285070

# get (index or ID) of start, end of csv
start, end = get_candle_index(("2023-01-01","2026-02-23"))
lst_month_starts = get_month_start_indices(start, end, just_index= True)

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
    "rsi": {},
}


def _cached_indicator(kind, key, builder):
    cache = _INDICATOR_CACHE[kind]
    if key not in cache:
        cache[key] = builder()
    return cache[key]

# Main Trading Logic
def rsi_strategy(tune: dict = None):

    # detect optimization mode early so we can disable I/O and heavy bookkeeping
    optimize = bool(tune.get('optimize')) if tune else False
    verbose = not optimize
    csv_logger = TradeCSVLogger(optimize=optimize)

    # ---- settings ----
    # Capital & position sizing
    balance = 1000                  # base balance
    leverage = 1                   # default leverage
    trade_amount_percent = 0.10      # 10% of balance per trade

    save_money = 0
    symbol_change_pct = 0.01
    more_symbol_change_pct = 0.05
    rsi_symbol_change_pct = 0.02
    rsi_value_close_positions = 90
    max_open_trades = 5  # 1 = single-position mode, >1 allows multiple concurrent positions
    max_trade_change_pct = 0.0
    static_dynamic_money_pct = 0.90

    # rsi sets
    rsi_buy_value = 30

    # Safe leverage levels
    safe_leverage_low = 1
    safe_leverage_med = 1
    safe_leverage_high = 1

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
    monthly_profit_close_filter = False
    monthly_loss_close_filter = False

    # Filters & behavior switches
    adx_filter = False
    volume_filter = False
    atr_filter = False
    consecutive_losses_month_stop_filter = False
    skip_logic = False
    add_remove_maxtrades_power = True
    original_max_open_trades = max_open_trades

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
    loss_exit_pct_1 = 0.05  # 5% loss threshold
    loss_exit_pct_2 = 0.04  # 4% loss threshold
    profit_exit_pct_1 = 0.15  # 15% profit threshold
    profit_exit_pct_2 = 0.10  # 7% profit threshold
    loss_lock_step_pct = 0.01  # step % for locking in losses (trailing loss target)
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
    period_rsi = 10
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
        if 'loss_exit_pct_1' in tune:
            loss_exit_pct_1 = float(tune['loss_exit_pct_1'])

        if 'loss_exit_pct_2' in tune:
            loss_exit_pct_2 = float(tune['loss_exit_pct_2'])

        if 'exit_score_loss_guard_1' in tune:
            exit_score_loss_guard_1 = int(tune['exit_score_loss_guard_1'])

        if 'exit_score_loss_guard_2' in tune:
            exit_score_loss_guard_2 = int(tune['exit_score_loss_guard_2'])

        if 'profit_exit_pct_1' in tune:
            profit_exit_pct_1 = float(tune['profit_exit_pct_1'])

        if 'profit_exit_pct_2' in tune:
            profit_exit_pct_2 = float(tune['profit_exit_pct_2'])

        if 'exit_score_profit_guard_1' in tune:
            exit_score_profit_guard_1 = int(tune['exit_score_profit_guard_1'])

        if 'exit_score_profit_guard_2' in tune:
            exit_score_profit_guard_2 = int(tune['exit_score_profit_guard_2'])   

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

        if 'loss_lock_step_pct' in tune:
            loss_lock_step_pct = float(tune['loss_lock_step_pct'])

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

        if 'scale_entry_amount_percent' in tune:
            scale_entry_amount_percent = float(tune['scale_entry_amount_percent'])
        elif 'trade_amount_percent_neworder' in tune:
            # backward compatibility with previous parameter name
            scale_entry_amount_percent = float(tune['trade_amount_percent_neworder'])

        if 'scale_entry_profit_trigger_pct' in tune:
            scale_entry_profit_trigger_pct = float(tune['scale_entry_profit_trigger_pct'])

        if 'scale_entry_loss_trigger_pct' in tune:
            scale_entry_loss_trigger_pct = float(tune['scale_entry_loss_trigger_pct'])

        if 'scale_entry_trigger_pct' in tune:
            # backward compatibility with shared trigger parameter
            shared_scale_entry_trigger_pct = float(tune['scale_entry_trigger_pct'])
            scale_entry_profit_trigger_pct = shared_scale_entry_trigger_pct
            scale_entry_loss_trigger_pct = shared_scale_entry_trigger_pct
        elif 'scale_in_trigger_move_pct' in tune:
            # backward compatibility with previous parameter name
            legacy_scale_entry_trigger_pct = float(tune['scale_in_trigger_move_pct'])
            scale_entry_profit_trigger_pct = legacy_scale_entry_trigger_pct
            scale_entry_loss_trigger_pct = legacy_scale_entry_trigger_pct

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

        if 'scale_in_enabled' in tune:
            scale_in_enabled = bool(tune['scale_in_enabled'])

        if 'scale_entry_on_profit_enabled' in tune:
            scale_entry_on_profit_enabled = bool(tune['scale_entry_on_profit_enabled'])

        if 'scale_entry_on_loss_enabled' in tune:
            scale_entry_on_loss_enabled = bool(tune['scale_entry_on_loss_enabled'])

        if 'loss_scale_entry_filter_enabled' in tune:
            loss_scale_entry_filter_enabled = bool(tune['loss_scale_entry_filter_enabled'])

        if 'loss_scale_entry_min_score' in tune:
            loss_scale_entry_min_score = int(tune['loss_scale_entry_min_score'])

        if 'loss_scale_entry_atr_ratio_min' in tune:
            loss_scale_entry_atr_ratio_min = float(tune['loss_scale_entry_atr_ratio_min'])
        else:
            # backward compatibility with older split params
            if 'loss_scale_entry_long_atr_ratio_min' in tune:
                loss_scale_entry_atr_ratio_min = float(tune['loss_scale_entry_long_atr_ratio_min'])
            if 'loss_scale_entry_short_atr_ratio_min' in tune:
                loss_scale_entry_atr_ratio_min = float(tune['loss_scale_entry_short_atr_ratio_min'])

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

        if 'max_open_trades' in tune:
            max_open_trades = max(1, int(tune['max_open_trades']))
        
        if 'symbol_change_pct' in tune:
            symbol_change_pct = float(tune['symbol_change_pct'])

        if 'more_symbol_change_pct' in tune:
            more_symbol_change_pct = float(tune['more_symbol_change_pct'])
        
        if 'max_trade_change_pct' in tune:
            max_trade_change_pct = float(tune['max_trade_change_pct'])

        if 'static_dynamic_money_pct' in tune:
            static_dynamic_money_pct = float(tune['static_dynamic_money_pct'])

        if 'period_rsi' in tune:
            period_rsi = int(tune['period_rsi'])

        if 'rsi_buy_value' in tune:
            rsi_buy_value = int(tune['rsi_buy_value'])

        if 'rsi_symbol_change_pct' in tune:
            rsi_symbol_change_pct = float(tune['rsi_symbol_change_pct'])

        if 'rsi_value_close_positions' in tune:
            rsi_value_close_positions = float(tune['rsi_value_close_positions'])

    # ---- setting end ----
    multi_position_enabled = max_open_trades > 1
    if multi_position_enabled and verbose:
        print(f"ℹ️ Multi-position mode enabled (max_open_trades={max_open_trades}).")

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
    last_price_entry = 0
    remaining_open_margin = 0

    lst_profit_percent_per_month = []
    monthly_stop_reasons = []
    pending_monthly_stop_reason = None
    pending_monthly_stop_value = 0.0

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

    open_positions = []
    next_trade_id = 1
    atr_ratio = None

    # ---- Cross & Exit state and parameters ----
    cross_seen = False               # whether EMA16/MA50 have crossed at least once
    last_cross_dir = None           # 'bull' or 'bear'
    last_cross_index = None
    last_cross_strongest_up_move_pct = 0.0
    last_cross_strongest_down_move_pct = 0.0
    last_trade_cross_index = None   # index of the cross used to open the last trade
    trade_power = True

    # max open trades variables
    was_high_len_positions = False

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

    # ---- get RSI ----
    rsi_list = _cached_indicator(
        "rsi",
        period_rsi,
        lambda: indicator.get_RSI(close_prices, period=period_rsi),
    )

    def _count_open(side):
        return sum(1 for p in open_positions if p['side'] == side)

    # ---- MAIN ----
    for i in range(len(close_prices)):
        # print(start+i)

        
        # margin static
        total_open_margin_static = sum(p['margin'] for p in open_positions)

        # margin dynamic
        lst_open_margin_dynamic = []
        for p in open_positions:
            if p['side'] == "long":
                profit_open_positions_pct = ((close_prices[i] - p['entry_price']) / p['entry_price']) * 100
            if p['side'] == "short":
                profit_open_positions_pct = ((p['entry_price'] - close_prices[i]) / p['entry_price']) * 100
            profit_open_positions_pct_leverage = profit_open_positions_pct * p['leverage']
            lst_open_margin_dynamic.append(p['margin'] + p['margin'] * profit_open_positions_pct_leverage / 100)
        total_open_margin_dynamic = sum(lst_open_margin_dynamic)
        
        total_money_static = balance + total_open_margin_static + save_money
        total_money_dynamic = balance + total_open_margin_dynamic + save_money
        
        if chart_data is not None:
            chart_data.append([i, total_money_static, total_money_dynamic])

        if ema_16[i] is None or ma_50[i] is None or ma_100[i] is None or ma_200[i] is None:
            continue
        
        for p in open_positions:
            if p['target_close_price_loss'] is None:
                p['target_close_price_loss'] = p['entry_price']
            if p['side'] == "long":
                if close_prices[i] >= p['target_close_price_loss'] * (1 + loss_lock_step_pct):
                    p['target_close_price_loss'] = p['target_close_price_loss'] * (1 + loss_lock_step_pct)
            elif p['side'] == "short":
                if close_prices[i] <= p['target_close_price_loss'] * (1 - loss_lock_step_pct):
                    p['target_close_price_loss'] = p['target_close_price_loss'] * (1 - loss_lock_step_pct)

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
            elif len(open_positions) == 0:
                continue
        
        # monthly filter if profit/loss monthly stop toggles are active
        if monthly_profit_close_filter or monthly_loss_close_filter:
            if trade_power == False:
                if int(start+i) in lst_month_starts:
                    if pending_monthly_stop_reason == "profit":
                        stop_val = pending_monthly_stop_value if pending_monthly_stop_value is not None else profit_percent_per_month
                        lst_profit_percent_per_month.append(abs(stop_val))
                        monthly_stop_reasons.append("profit")
                    elif pending_monthly_stop_reason == "loss":
                        stop_val = pending_monthly_stop_value if pending_monthly_stop_value is not None else profit_percent_per_month
                        lst_profit_percent_per_month.append(-abs(stop_val))
                        monthly_stop_reasons.append("loss")
                    else:
                        lst_profit_percent_per_month.append(profit_percent_per_month)
                    profit_percent_per_month = 0
                    pending_monthly_stop_reason = None
                    pending_monthly_stop_value = 0.0
                    trade_power = True 
                elif len(open_positions) == 0:
                    continue
        
        # cooldown after good profit
        if i < cooldown_until_index and len(open_positions) == 0:
            continue
        
        # Calculate MA Distance
        ma_distance = abs(ema_16[i] - ma_50[i]) / ma_50[i]

        # Calculate Distance New Candle Move and Last Candle Move
        if i > 0:
            last_candle_move = abs(close_prices[i] - open_prices[i]) / open_prices[i]
        else:
            last_candle_move = 0

        # Calculate total balance (if we have order we have: margin + balance)
        margin_balance = balance + sum(p['margin'] for p in open_positions)
        balance_before_close_batch = balance
        balance_before_close_batch_no_fee = balance_without_fee
        balance_before_close_batch_total = balance_before_close_batch + sum(p['margin'] for p in open_positions)

        # ===================== CHECK LIQUIDATION =====================
        liquidated_any = False
        for p in open_positions[:]:
            if p['side'] == "long":
                remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                liq_updates = trade_manager.check_liquidation_long(
                    i,
                    low_prices,
                    close_times,
                    p['entry_price'],
                    p['leverage'],
                    p['margin'],
                    balance,
                    balance_without_fee,
                    deducting_fee_total,
                    count_closed_orders,
                    total_losses,
                    total_long,
                    equity_curve,
                    save_money,
                    max_drawdown,
                    p['open_time_value'],
                    csv_logger,
                    trade_amount_percent,
                    total_liquids,
                    p['trade_id'],
                    remaining_open_margin,
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    balance_before_close_batch_total
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
                    open_positions.remove(p)
                    liquidated_any = True
                    if consecutive_losses_month_stop_filter:
                        loss_streak_until_month_stop += 1
                        if (
                            consecutive_losses_stop_until_month > 0
                            and loss_streak_until_month_stop >= consecutive_losses_stop_until_month
                        ):
                            stop_trading_until_new_month_by_losses = True
                            loss_streak_until_month_stop = 0
                    if long_close_points is not None:
                        long_close_points.append((i, liq_updates['close_price']))
                        if long_close_reasons is not None:
                            long_close_reasons[i] = liq_reason_text
            elif p['side'] == "short":
                remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                liq_updates = trade_manager.check_liquidation_short(
                    i,
                    high_prices,
                    close_times,
                    p['entry_price'],
                    p['leverage'],
                    p['margin'],
                    balance,
                    balance_without_fee,
                    deducting_fee_total,
                    count_closed_orders,
                    total_losses,
                    total_short,
                    equity_curve,
                    save_money,
                    max_drawdown,
                    p['open_time_value'],
                    csv_logger,
                    trade_amount_percent,
                    total_liquids,
                    p['trade_id'],
                    remaining_open_margin,
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    balance_before_close_batch_total
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
                    open_positions.remove(p)
                    liquidated_any = True
                    if consecutive_losses_month_stop_filter:
                        loss_streak_until_month_stop += 1
                        if (
                            consecutive_losses_stop_until_month > 0
                            and loss_streak_until_month_stop >= consecutive_losses_stop_until_month
                        ):
                            stop_trading_until_new_month_by_losses = True
                            loss_streak_until_month_stop = 0
                    if short_close_points is not None:
                        short_close_points.append((i, liq_updates['close_price']))
                        if short_close_reasons is not None:
                            short_close_reasons[i] = liq_reason_text
        if liquidated_any:
            continue
        

        if last_price_entry <= close_prices[i]:
            last_price_entry = close_prices[i]

        if add_remove_maxtrades_power:
            if (last_price_entry * (1 - max_trade_change_pct) > close_prices[i]) and len(open_positions) == max_open_trades:
                max_open_trades += original_max_open_trades

            if len(open_positions) == max_open_trades:
                was_high_len_positions = True

            if (len(open_positions) <= max_open_trades - original_max_open_trades) and (was_high_len_positions is True):
                max_open_trades = max(original_max_open_trades, max_open_trades - original_max_open_trades)
                was_high_len_positions = False

        # ===================== OPEN LONG =====================
        if (close_prices[i] <= last_price_entry * (1 - symbol_change_pct)) and (len(open_positions) < max_open_trades) and rsi_list[i] <= rsi_buy_value:
            # ---- open long ----
            updates = trade_manager.open_long(
                i,
                close_prices,
                close_times,
                balance,
                balance_without_fee,
                trade_amount_percent,
                margin_balance)

            if updates is not None:
                balance = updates['balance']
                balance_without_fee = updates['balance_without_fee']
                position = {
                    'trade_id': next_trade_id,
                    'side': "long",
                    'entry_price': updates['entry_price'],
                    'entry_index': i,
                    'highest_since_entry': max(updates['entry_price'], high_prices[i]),
                    'lowest_since_entry': min(updates['entry_price'], low_prices[i]),
                    'position_size': updates['position_size'],
                    'position_size_no_fee': updates['position_size_no_fee'],
                    'balance_before_trade': updates['balance_before_trade'],
                    'balance_before_trade_no_fee': updates['balance_before_trade_no_fee'],
                    'margin': updates['margin'],
                    'margin_no_fee': updates['margin_no_fee'],
                    'leverage': updates['leverage'],
                    'open_time_value': updates['open_time_value'],
                    'target_close_price_loss': updates['entry_price'],
                }
                open_positions.append(position)
                last_price_entry = close_prices[i]
                next_trade_id += 1
                if long_open_points is not None:
                    long_open_points.append((i, position['entry_price']))
                    if long_open_reasons is not None:
                        entry_reason_text = f"open this order because from last entry come down {symbol_change_pct * 100}% \n len opened orders: {len(open_positions)}"
                        long_open_reasons[i] = entry_reason_text
                # record which cross enabled this trade and init trailing state
                last_trade_cross_index = last_cross_index

                updates = None

        # ===================== CLOSE LONG =====================
        long_positions_to_close = [p for p in open_positions if p['side'] == "long"]
        for p in long_positions_to_close:
            close_reason1 = p['entry_price'] * (1 + more_symbol_change_pct) <= close_prices[i]
            close_reason2 = rsi_list[i] >= rsi_value_close_positions and p['entry_price'] * (1 + rsi_symbol_change_pct) <= close_prices[i]
            if close_reason1 or close_reason2:
                updates = trade_manager.close_long(
                    i,
                    close_prices,
                    close_times,
                    p['entry_price'],
                    p['position_size'],
                    p['position_size_no_fee'],
                    fee_rate,
                    p['margin'],
                    p['margin_no_fee'],
                    balance,
                    balance_without_fee,
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
                    p['leverage'],
                    cooldown_until_index,
                    p['open_time_value'],
                    csv_logger,
                    trade_amount_percent,
                    profit_percent_per_month,
                    save_money,
                    trade_power,
                    p['trade_id'],
                    remaining_open_margin,
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    balance_before_close_batch_total)

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
                profit_percent_per_month = updates['profit_percent_per_month']
                save_money = updates['save_money']
                trade_power = updates['trade_power']
                if updates.get('monthly_stop_reason') is not None:
                    pending_monthly_stop_reason = updates.get('monthly_stop_reason')
                    pending_monthly_stop_value = updates.get('monthly_stop_value')
                open_positions.remove(p)
                updates = None
                if long_close_points is not None:
                    long_close_points.append((i, close_prices[i]))
                    if long_close_reasons is not None:
                        if close_reason1:
                            long_close_reasons[i] = f"close ID: {p['trade_id']} for moving upper than {round((symbol_change_pct + more_symbol_change_pct) * 100, 2)}%\n"
                        if close_reason2:
                            long_close_reasons[i] = f"rsi is more than {rsi_value_close_positions}({rsi_list[i]})\n and we got more than {rsi_value_close_positions}%"

                            
    # ===================== BACKTEST SUMMARY =====================

    if open_positions:
        balance += sum(p['margin'] for p in open_positions)
        balance_without_fee += sum(p['margin_no_fee'] for p in open_positions)

    balance += save_money

    # summary calculation
    t_profit_percent = balance * 100 / first_balance - 100
    days, hours, minutes = trade_duration(first_open_time, last_close_time)
    win_rate = (total_wins / (total_wins + total_losses)) * 100 if (total_wins + total_losses) > 0 else 0


    if monthly_stop_reasons:
        profit_months_count = sum(1 for r in monthly_stop_reasons if r == "profit")
        loss_months_count = sum(1 for r in monthly_stop_reasons if r == "loss")
    else:
        # fallback: keep previous behavior when no explicit monthly stop reason exists
        profit_months_count = sum(1 for p in lst_profit_percent_per_month if p > 0)
        loss_months_count = sum(1 for p in lst_profit_percent_per_month if p < 0)

    if verbose:
        print("✅ BACKTEST FINISHED")
        print("Closed Trades:", count_closed_orders, "( Longs:", total_long, "| Shorts:", total_short, ")")
        print("Count open Trades:", len(open_positions))
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
            rsi_values=rsi_list,
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
    rsi_strategy()

# print(open_prices[0])
# print(open_times[0])
# print(open_times[1])
# print(start, end)
# print(lst_month_starts)
# print(get_candle_index("2025-03-01"))
# print(get_candle_index("2025-02-27"))
