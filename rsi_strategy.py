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
from generate_reason_text import generate_entry_reason_text, generate_close_reason_text
from strategy_config import build_rsi_strategy_config


# start = get_candle_index("2025-01-01")   ----> 244944
# end = get_candle_index("2026-02-23")     ----> 285070

# get (index or ID) of start, end of csv
start, end = get_candle_index(("2025-01-01","2026-02-23"))
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
    cfg = build_rsi_strategy_config(tune)
    balance = cfg.balance
    leverage = cfg.leverage
    trade_amount_percent = cfg.trade_amount_percent
    scale_entry_amount_percent = cfg.scale_entry_amount_percent
    scale_entry_profit_trigger_pct = cfg.scale_entry_profit_trigger_pct
    scale_entry_loss_trigger_pct = cfg.scale_entry_loss_trigger_pct
    save_money = cfg.save_money
    symbol_change_pct = cfg.symbol_change_pct
    more_symbol_change_pct = cfg.more_symbol_change_pct
    rsi_symbol_change_pct = cfg.rsi_symbol_change_pct
    max_open_trades = cfg.max_open_trades
    max_trade_change_pct = cfg.max_trade_change_pct
    static_dynamic_money_pct = cfg.static_dynamic_money_pct
    rsi_open_value = cfg.rsi_open_value
    rsi_close_value = cfg.rsi_close_value
    safe_leverage_low = cfg.safe_leverage_low
    safe_leverage_med = cfg.safe_leverage_med
    safe_leverage_high = cfg.safe_leverage_high
    safe_leverage_balance_pct_low = cfg.safe_leverage_balance_pct_low
    safe_leverage_balance_pct_med = cfg.safe_leverage_balance_pct_med
    safe_leverage_balance_pct_high = cfg.safe_leverage_balance_pct_high
    save_money_recover_trigger_pct = cfg.save_money_recover_trigger_pct
    monthly_profit_percent_stop_trade = cfg.monthly_profit_percent_stop_trade
    monthly_loss_percent_stop_trade = cfg.monthly_loss_percent_stop_trade
    monthly_compound = cfg.monthly_compound
    monthly_profit_close_filter = cfg.monthly_profit_close_filter
    monthly_loss_close_filter = cfg.monthly_loss_close_filter
    adx_filter = cfg.adx_filter
    volume_filter = cfg.volume_filter
    atr_filter = cfg.atr_filter
    consecutive_losses_month_stop_filter = cfg.consecutive_losses_month_stop_filter
    skip_logic = cfg.skip_logic
    add_remove_maxtrades_power = cfg.add_remove_maxtrades_power
    original_max_open_trades = max_open_trades
    cooldown_after_big_pnl = cfg.cooldown_after_big_pnl
    cooldown_until_index = -1
    ma_distance_threshold = cfg.ma_distance_threshold
    candle_move_threshold = cfg.candle_move_threshold
    impulse_move_threshold_pct = cfg.impulse_move_threshold_pct
    impulse_lookback = cfg.impulse_lookback
    late_entry_atr_mult = cfg.late_entry_atr_mult
    late_entry_body_ratio = cfg.late_entry_body_ratio
    late_entry_ema_pct = cfg.late_entry_ema_pct
    entry_score_threshold = cfg.entry_score_threshold
    exit_score_threshold = cfg.exit_score_threshold
    slope_window = cfg.slope_window
    trail_activate_pct = cfg.trail_activate_pct
    trail_retrace_pct = cfg.trail_retrace_pct
    loss_exit_pct_1 = cfg.loss_exit_pct_1
    loss_exit_pct_2 = cfg.loss_exit_pct_2
    profit_exit_pct_1 = cfg.profit_exit_pct_1
    profit_exit_pct_2 = cfg.profit_exit_pct_2
    loss_lock_step_pct = cfg.loss_lock_step_pct
    adx_exit_threshold = cfg.adx_exit_threshold
    adx_exit_lookback = cfg.adx_exit_lookback
    entry_adx_threshold = cfg.entry_adx_threshold
    entry_atr_threshold = cfg.entry_atr_threshold
    opposite_atr_body_mult = cfg.opposite_atr_body_mult
    sharp_move_threshold_pct = cfg.sharp_move_threshold_pct
    sharp_move_lookback_candles = cfg.sharp_move_lookback_candles
    post_cross_penalty_candles = cfg.post_cross_penalty_candles
    consecutive_losses_stop_until_month = cfg.consecutive_losses_stop_until_month
    period_adx = cfg.period_adx
    period_atr = cfg.period_atr
    period_atr_ma = cfg.period_atr_ma
    period_vol_avg = cfg.period_vol_avg
    period_rsi = cfg.period_rsi
    volume_spike_multiplier = cfg.volume_spike_multiplier
    plot_max_candles = cfg.plot_max_candles
    plot_end_offset = cfg.plot_end_offset
    plot_step_candles = cfg.plot_step_candles
    plot_min_zoom_candles = cfg.plot_min_zoom_candles
    plot_max_render_candles = cfg.plot_max_render_candles
    plot_zoom_in_factor = cfg.plot_zoom_in_factor
    plot_zoom_out_factor = cfg.plot_zoom_out_factor
    plot_window_width_scale = cfg.plot_window_width_scale
    plot_window_height_scale = cfg.plot_window_height_scale
    plot_drag_preview_factor = cfg.plot_drag_preview_factor
    plot_drag_update_interval_ms = cfg.plot_drag_update_interval_ms
    plot_yscale_drag_sensitivity = cfg.plot_yscale_drag_sensitivity
    plot_post_cross_penalty_markers = cfg.plot_post_cross_penalty_markers
    entry_score_cross = cfg.entry_score_cross
    entry_score_ema_vs_ma50 = cfg.entry_score_ema_vs_ma50
    entry_score_ma_trend = cfg.entry_score_ma_trend
    entry_score_ma_distance_or_candle = cfg.entry_score_ma_distance_or_candle
    entry_score_adx = cfg.entry_score_adx
    entry_score_volume = cfg.entry_score_volume
    entry_late_penalty = cfg.entry_late_penalty
    exit_score_loss_guard_1 = cfg.exit_score_loss_guard_1
    exit_score_loss_guard_2 = cfg.exit_score_loss_guard_2
    exit_score_profit_guard_1 = cfg.exit_score_profit_guard_1
    exit_score_profit_guard_2 = cfg.exit_score_profit_guard_2
    exit_score_ema_slope = cfg.exit_score_ema_slope
    exit_score_ema_cross = cfg.exit_score_ema_cross
    exit_score_ma_trend = cfg.exit_score_ma_trend
    exit_score_trailing = cfg.exit_score_trailing
    exit_score_adx = cfg.exit_score_adx
    exit_score_opposite_candle = cfg.exit_score_opposite_candle
    post_cross_penalty_score = cfg.post_cross_penalty_score

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
    ema_16_period = cfg.ema_16_period
    ma_50_period = cfg.ma_50_period
    ma_100_period = cfg.ma_100_period
    ma_200_period = cfg.ma_200_period

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
        open_reason1 = (close_prices[i] <= last_price_entry * (1 - symbol_change_pct)) and (len(open_positions) < max_open_trades) and (rsi_list[i] <= rsi_open_value)
        open_reason2 = (rsi_list[i] <= 20) and (len(open_positions) < max_open_trades + 2)
        if open_reason1 or open_reason2:
            # ---- open long ----
            updates = trade_manager.open_long(
                i,
                close_prices,
                close_times,
                balance,
                balance_without_fee,
                trade_amount_percent,
                margin_balance,
                tactical_balance)

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
                
                # open point on chart
                if long_open_points is not None:
                    long_open_points.append((i, position['entry_price']))
                    # open reason text
                    if long_open_reasons is not None:
                        # default texts
                        entry_reason_text = generate_entry_reason_text(trade_id=next_trade_id, updates=updates)
                        if open_reason1:
                            entry_reason_text += f"\nrsi is less than {rsi_open_value}({rsi_list[i]}) and price is less than last_entry"
                        long_open_reasons[i] = entry_reason_text
                
                next_trade_id += 1
                # record which cross enabled this trade and init trailing state
                last_trade_cross_index = last_cross_index
                updates = None

        # ===================== CLOSE LONG =====================
        long_positions_to_close = [p for p in open_positions if p['side'] == "long"]
        for p in long_positions_to_close:
            close_reason1 = p['entry_price'] * (1 + more_symbol_change_pct) <= close_prices[i]
            close_reason2 = rsi_list[i] >= rsi_close_value and p['entry_price'] * (1 + rsi_symbol_change_pct) <= close_prices[i]
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
                    tactical_balance,
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
                # remove position
                open_positions.remove(p)
                
                # close point on chart
                if long_close_points is not None:
                    long_close_points.append((i, close_prices[i]))
                    # close reason text
                    if long_close_reasons is not None:
                        exit_reason_text = generate_close_reason_text(trade_id=p['trade_id'], updates=updates)
                        if close_reason1:
                            exit_reason_text += f"\nclose ID: {p['trade_id']} for moving upper than {round((symbol_change_pct + more_symbol_change_pct) * 100, 2)}%"
                        if close_reason2:
                            exit_reason_text += f"\nrsi is more than {rsi_close_value}({rsi_list[i]})\n and we got more than {rsi_symbol_change_pct * 100}%"
                        
                        long_close_reasons[i] = exit_reason_text
                        
                updates = None

                used_save_money_for_monthly_loss = False
                monthly_stop_reason = None
                monthly_stop_value = None
                log_tactical_balance = tactical_balance

                # stop trade if we got monthly target profit
                # Apply monthly actions only after the last close in a batch.
                if trade_power and remaining_open_margin <= 0 and monthly_profit_close_filter == True :
                    if profit_percent_per_month >= monthly_profit_percent_stop_trade:
                        monthly_stop_reason = "profit"
                        monthly_stop_value = profit_percent_per_month
                        tactical_balance = tactical_balance + (tactical_balance * monthly_compound / 100)
                        monthly_surplus = balance - tactical_balance
                        if monthly_surplus > 0:
                            save_money += monthly_surplus
                        balance = tactical_balance
                        cooldown_until_index = i
                        trade_power = False    # off

                # stop trade if we got monthly max loss
                if trade_power and remaining_open_margin <= 0 and monthly_loss_close_filter == True:
                    if profit_percent_per_month <= -monthly_loss_percent_stop_trade:
                        monthly_stop_reason = "loss"
                        monthly_stop_value = profit_percent_per_month
                        needed_to_tactical = tactical_balance - balance
                        if needed_to_tactical > 0 and save_money >= needed_to_tactical:
                            balance += needed_to_tactical
                            save_money -= needed_to_tactical
                            used_save_money_for_monthly_loss = True

                    if profit_percent_per_month <= -monthly_loss_percent_stop_trade:
                        cooldown_until_index = i
                        trade_power = False    # off

                if monthly_profit_close_filter == False and monthly_loss_close_filter == False:
                    if balance >= tactical_balance * 1.08:
                        tactical_balance = balance

                # ---- save money ----
                # Recovery trigger must use active portfolio capital (free balance + other open margins),
                # not only free balance; otherwise multi-position mode withdraws too early.
                if trade_power and (not used_save_money_for_monthly_loss):
                    save_money_recover_amount_pct = 100 - save_money_recover_trigger_pct
                    active_capital = balance + remaining_open_margin
                    recover_trigger_capital = tactical_balance * save_money_recover_trigger_pct / 100
                    recover_amount = tactical_balance * save_money_recover_amount_pct / 100
                    if active_capital < recover_trigger_capital:
                        if save_money >= recover_amount:
                            balance += recover_amount
                            save_money -= recover_amount

                pending_monthly_stop_reason = monthly_stop_reason
                pending_monthly_stop_value = monthly_stop_value

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
        print("Final balance if close, open orders:", round(total_money_dynamic, 2), "$")
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
        'final_balance_static': total_money_static,
        "final_balance_dynamic": total_money_dynamic,
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
