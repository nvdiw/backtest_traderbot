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
from fetch_calculate_data import fetch_all_data, trade_duration
from generate_reason_text import generate_entry_reason_text, generate_close_reason_text
from strategy_config import build_ma_strategy_config


# start = get_candle_index("2018-01-01")   ----> 1 on CSV
# end = get_candle_index("2026-05-31")     ----> 294381 on CSV

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
def ma_strategy(tune: dict = None):

    # detect optimization mode early so we can disable I/O and heavy bookkeeping
    optimize = bool(tune.get('optimize')) if tune else False
    verbose = not optimize
    csv_logger = TradeCSVLogger(optimize=optimize)

    # ---- settings ----
    cfg = build_ma_strategy_config(tune)
    balance = cfg.balance
    leverage = cfg.leverage
    trade_amount_percent = cfg.trade_amount_percent
    scale_entry_amount_percent = cfg.scale_entry_amount_percent
    scale_entry_profit_trigger_pct = cfg.scale_entry_profit_trigger_pct
    scale_entry_loss_trigger_pct = cfg.scale_entry_loss_trigger_pct
    save_money = cfg.save_money
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
    scale_entry_on_profit_enabled = cfg.scale_entry_on_profit_enabled
    scale_entry_on_loss_enabled = cfg.scale_entry_on_loss_enabled
    scale_in_enabled = cfg.scale_in_enabled
    profit_scale_entry_filter_enabled = cfg.profit_scale_entry_filter_enabled
    profit_scale_entry_min_score = cfg.profit_scale_entry_min_score
    profit_scale_entry_atr_ratio_min = cfg.profit_scale_entry_atr_ratio_min
    adx_filter = cfg.adx_filter
    volume_filter = cfg.volume_filter
    atr_filter = cfg.atr_filter
    consecutive_losses_month_stop_filter = cfg.consecutive_losses_month_stop_filter
    skip_logic = cfg.skip_logic
    max_open_trades = cfg.max_open_trades
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
    fee_rate = cfg.fee_rate
    rsi_trade_monthly_filter_on = cfg.rsi_trade_monthly_filter_on
    rsi_long_open_monthly_profit = cfg.rsi_long_open_monthly_profit
    rsi_long_close_monthly_profit = cfg.rsi_long_close_monthly_profit
    rsi_short_open_monthly_profit = cfg.rsi_short_open_monthly_profit
    rsi_short_close_monthly_profit = cfg.rsi_short_close_monthly_profit
    rsi_long_tp_pct = cfg.rsi_long_tp_pct
    rsi_long_sl_pct = cfg.rsi_long_sl_pct
    rsi_short_tp_pct = cfg.rsi_short_tp_pct
    rsi_short_sl_pct = cfg.rsi_short_sl_pct
    rsi_max_open_trades = cfg.rsi_max_open_trades
    rsi_trade_amount_percent = cfg.rsi_trade_amount_percent
    rsi_leverage = cfg.rsi_leverage
    rsi_cooldown_bars = cfg.rsi_cooldown_bars
    rsi_cooldown_filter = cfg.rsi_cooldown_filter
    lowest_rsi_last_n_value = cfg.lowest_rsi_last_n_value
    highest_rsi_last_n_value = cfg.highest_rsi_last_n_value
    rsi_entry_buffer = cfg.rsi_entry_buffer
    rsi_distance_threshold = cfg.rsi_distance_threshold
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
        lines.append(f"Threshold: {threshold}\n")
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

    # ===================== SCALE VARIABLES =====================
    # SCALE ENTRY STATISTICS - LONG
    # ==========================================================

    # Triggered opportunities
    long_profit_scale_entry_attempts = 0
    long_loss_scale_entry_attempts = 0

    # Rejected by filters
    long_filtered_profit_scale_entries = 0

    # Executed entries
    long_profit_scale_entries = 0
    long_loss_scale_entries = 0


    # ==========================================================
    # SCALE ENTRY STATISTICS - SHORT
    # ==========================================================

    # Triggered opportunities
    short_profit_scale_entry_attempts = 0
    short_loss_scale_entry_attempts = 0

    # Rejected by filters
    short_filtered_profit_scale_entries = 0

    # Executed entries
    short_profit_scale_entries = 0
    short_loss_scale_entries = 0


    # ==========================================================
    # SCALE PERFORMANCE - LONG
    # ==========================================================

    scale_ma_long_total = 0
    scale_ma_long_wins = 0
    scale_ma_long_losses = 0
    scale_ma_long_total_profit = 0.0


    # ==========================================================
    # SCALE PERFORMANCE - SHORT
    # ==========================================================

    scale_ma_short_total = 0
    scale_ma_short_wins = 0
    scale_ma_short_losses = 0
    scale_ma_short_total_profit = 0.0



    # ========== RSI LONG STATS INIT ==========
    rsi_long_total = 0
    rsi_long_wins = 0
    rsi_long_losses = 0
    rsi_long_total_profit = 0.0

    # ========== RSI SHORT STATS INIT ==========
    rsi_short_total = 0
    rsi_short_wins = 0
    rsi_short_losses = 0
    rsi_short_total_profit = 0.0

    # rsi_profit_calculator
    rsi_profit_calculator = 0

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

    # variables of rsi on monthly filter
    rsi_last_index_stop_loss_bar = 0
    rsi_in_cooldown = False

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

    # you can use times for open/close orders
    # # ---- time filter mask (13:30 UTC close time) ----
    # close_times_utc = pd.to_datetime(close_times, utc=True)
    # time_1330_mask = (close_times_utc.hour == 13) & (close_times_utc.minute == 30)

    #   # check data loaded correctly :
    # print(len(open_prices), "candles loaded.")
    # print("len(ema_16):", len(ema_16))
    # print("len(ma_50):", len(ma_50))
    # print("len adx:", len(adx))

    def _count_open(side):
        return sum(1 for p in open_positions if p['side'] == side)

    def _position_equity(position, price):
        if position['side'] == "long":
            pnl_pct = ((price - position['entry_price']) / position['entry_price']) * 100
        else:
            pnl_pct = ((position['entry_price'] - price) / position['entry_price']) * 100
        return position['margin'] + position['margin'] * pnl_pct * position['leverage'] / 100

    def _open_positions_equity(price, exclude_position=None):
        return sum(_position_equity(p, price) for p in open_positions if p is not exclude_position)

    # ---- MAIN ----
    for i in range(len(close_prices)):
        # print(start+i)

        # margin static
        total_open_margin_static = sum(p['margin'] for p in open_positions)

        # margin dynamic
        total_open_margin_dynamic = _open_positions_equity(close_prices[i])

        total_money_static = balance + total_open_margin_static + save_money
        total_money_dynamic = balance + total_open_margin_dynamic + save_money
        equity_curve, max_drawdown = trade_manager._update_drawdown(
            equity_curve,
            max_drawdown,
            total_money_dynamic
        )

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
        
        # ===================== CHECK LIQUIDATION =====================
        liquidated_any = False
        for p in open_positions[:]:
            if p['side'] == "long":
                remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                remaining_open_margin_no_fee = sum(x['margin_no_fee'] for x in open_positions if x is not p)
                # remaining_open_equity = _open_positions_equity(close_prices[i], p)
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
                    p['trade_amount_percent'],
                    total_liquids,
                    p['trade_id'],
                    remaining_open_margin,
                    remaining_open_margin_no_fee,
                    tactical_balance,
                    p['reason'],
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    p['balance_before_trade'],
                    p['balance_before_trade_no_fee'],
                    remaining_open_equity=remaining_open_margin
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
                remaining_open_margin_no_fee = sum(x['margin_no_fee'] for x in open_positions if x is not p)
                # remaining_open_equity = _open_positions_equity(close_prices[i], p)
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
                    p['trade_amount_percent'],
                    total_liquids,
                    p['trade_id'],
                    remaining_open_margin,
                    remaining_open_margin_no_fee,
                    tactical_balance,
                    p['reason'],
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    p['balance_before_trade'],
                    p['balance_before_trade_no_fee'],
                    remaining_open_equity=remaining_open_margin
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

        if rsi_trade_monthly_filter_on:
            # ---- close long when monthly filter is on
            long_positions_to_close = [p for p in open_positions[:] if p['side'] == "long" and p['reason'] == 'rsi_ma_strategy']
            for p in long_positions_to_close:
                if rsi_list[i] >= rsi_long_close_monthly_profit or close_prices[i] >= p['entry_price'] * (1 + rsi_long_tp_pct) or close_prices[i] <= p['entry_price'] * (1 - rsi_long_sl_pct):
                    remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                    remaining_open_margin_no_fee = sum(x['margin_no_fee'] for x in open_positions if x is not p)
                    # remaining_open_equity = _open_positions_equity(close_prices[i], p)
                    close_price = close_prices[i]
                    # ---- close long ----
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
                        p['trade_amount_percent'],
                        profit_percent_per_month,
                        save_money,
                        trade_power,
                        p['trade_id'],
                        remaining_open_margin,
                        remaining_open_margin_no_fee,
                        tactical_balance,
                        p['reason'],
                        balance_before_close_batch,
                        balance_before_close_batch_no_fee,
                        p['balance_before_trade'],
                        p['balance_before_trade_no_fee'],
                        remaining_open_equity=remaining_open_margin)

                    balance = updates['balance']
                    balance_without_fee = updates['balance_without_fee']
                    deducting_fee_total = updates['deducting_fee_total']
                    profits_lst = updates['profits_lst']
                    profit_order = updates['profit']
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
                    
                    # sum all profits
                    rsi_profit_calculator += profit_order

                    # close point on chart
                    if long_close_points is not None:
                        long_close_points.append((i, close_price))
                        # close reason text
                        if long_close_reasons is not None:
                            long_exit_reason_text = f"closed long when monthly filter is on and rsi is upper than: {rsi_long_close_monthly_profit}\n"
                            long_exit_reason_text += generate_close_reason_text(trade_id=p['trade_id'], updates=updates)
                            long_close_reasons[i] = long_exit_reason_text
                    
                    # calculate last stop loss with rsi on mothly filter
                    if rsi_cooldown_filter:
                        if profit_order < 0:
                            rsi_in_cooldown = True
                            rsi_last_index_stop_loss_bar = i

                    # ---- RSI LONG STATS ----
                    rsi_long_total += 1

                    if profit_order > 0:
                        rsi_long_wins += 1
                    else:
                        rsi_long_losses += 1

                    rsi_long_total_profit += profit_order


                    updates = None


            # ---- close short when monthly filter is on
            short_positions_to_close = [p for p in open_positions[:] if p['side'] == "short" and p['reason'] == 'rsi_ma_strategy']
            for p in short_positions_to_close:
                if rsi_list[i] <= rsi_short_close_monthly_profit or close_prices[i] <= p['entry_price'] * (1 - rsi_short_tp_pct) or close_prices[i] >= p['entry_price'] * (1 + rsi_short_sl_pct):
                    remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                    remaining_open_margin_no_fee = sum(x['margin_no_fee'] for x in open_positions if x is not p)
                    # remaining_open_equity = _open_positions_equity(close_prices[i], p)
                    close_price = close_prices[i]
                    # ---- close short ----
                    updates = trade_manager.close_short(
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
                        total_wins_short,
                        total_losses,
                        total_short,
                        cooldown_after_big_pnl,
                        p['leverage'],
                        cooldown_until_index,
                        p['open_time_value'],
                        csv_logger,
                        p['trade_amount_percent'],
                        profit_percent_per_month,
                        save_money,
                        trade_power,
                        p['trade_id'],
                        remaining_open_margin,
                        remaining_open_margin_no_fee,
                        tactical_balance,
                        p['reason'],
                        balance_before_close_batch,
                        balance_before_close_batch_no_fee,
                        p['balance_before_trade'],
                        p['balance_before_trade_no_fee'],
                        remaining_open_equity=remaining_open_margin
                        )

                    balance = updates['balance']
                    balance_without_fee = updates['balance_without_fee']
                    deducting_fee_total = updates['deducting_fee_total']
                    profits_lst = updates['profits_lst']
                    profit_order = updates['profit']
                    total_profit_percent = updates['total_profit_percent']
                    count_closed_orders = updates['count_closed_orders']
                    equity_curve = updates['equity_curve']
                    max_drawdown = updates['max_drawdown']
                    total_wins = updates['total_wins']
                    total_wins_short = updates['total_wins_short']
                    total_losses = updates['total_losses']
                    total_short = updates['total_short']
                    cooldown_until_index = updates['cooldown_until_index']
                    profit_percent_per_month = updates['profit_percent_per_month']
                    save_money = updates['save_money']
                    trade_power = updates['trade_power']
                    # remove position
                    open_positions.remove(p)

                    rsi_profit_calculator += profit_order

                    # close point on chart
                    if short_close_points is not None:
                        short_close_points.append((i, close_price))
                        # close reason text
                        if short_close_reasons is not None:
                            short_exit_reason_text = f"closed short when monthly filter is on and rsi is lower than: {rsi_short_close_monthly_profit}\n"
                            short_exit_reason_text += generate_close_reason_text(trade_id=p['trade_id'], updates=updates)
                            short_close_reasons[i] = short_exit_reason_text
                    
                    # calculate last stop loss with rsi on mothly filter
                    if rsi_cooldown_filter:
                        if profit_order < 0:
                            rsi_in_cooldown = True
                            rsi_last_index_stop_loss_bar = i

                    # ---- RSI SHORT STATS ----
                    rsi_short_total += 1

                    if profit_order > 0:
                        rsi_short_wins += 1
                    else:
                        rsi_short_losses += 1

                    rsi_short_total_profit += profit_order


                    updates = None


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
                    if rsi_profit_calculator > 0:
                        save_money += rsi_profit_calculator
                        balance -= rsi_profit_calculator
                    rsi_profit_calculator = 0.0
                    trade_power = True 


                # ==== RSI OPEN LONG ====
                if rsi_trade_monthly_filter_on:

                    momentum_up = (
                        close_prices[i] > close_prices[i-1]
                        and close_prices[i-1] > close_prices[i-2]
                    )

                    lowest_rsi_last_n = min(rsi_list[i - lowest_rsi_last_n_value : i])

                    rsi_now = rsi_list[i]
                    rsi_prev = rsi_list[i-1]

                    rsi_rejection_up = rsi_prev < rsi_now

                    rsi_distance_up = rsi_now - lowest_rsi_last_n

                    if rsi_in_cooldown:
                        if i > rsi_last_index_stop_loss_bar + rsi_cooldown_bars:
                            rsi_in_cooldown = False

                    if (
                        lowest_rsi_last_n <= rsi_long_open_monthly_profit
                        and rsi_now <= min(100, rsi_long_open_monthly_profit + rsi_entry_buffer)
                        and rsi_rejection_up
                        and rsi_distance_up >= rsi_distance_threshold
                        and momentum_up
                        and len(open_positions) < rsi_max_open_trades
                        and not rsi_in_cooldown
                    ):
                        # ---- open long ----
                        updates = trade_manager.open_long(
                            i,
                            close_prices,
                            close_times,
                            balance,
                            balance_without_fee,
                            rsi_trade_amount_percent,
                            balance + sum(p['margin'] for p in open_positions),
                            balance_without_fee + sum(p['margin_no_fee'] for p in open_positions),
                            tactical_balance,
                            leverage = rsi_leverage,)
                        if updates is not None:

                            balance = updates['balance']
                            balance_without_fee = updates['balance_without_fee']
                            trade_reason = 'rsi_ma_strategy'
                            position = {
                                'trade_id': f"{trade_reason}_{next_trade_id:04d}",
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
                                'trade_amount_percent': updates['trade_amount_percent'],
                                'leverage': updates['leverage'],
                                'open_time_value': updates['open_time_value'],
                                'target_close_price_loss': updates['entry_price'],
                                'reason': trade_reason
                            }
                            open_positions.append(position)
                            
                            # open point on chart
                            if long_open_points is not None:
                                long_open_points.append((i, position['entry_price']))
                                # open reason text
                                if long_open_reasons is not None:
                                    # default texts
                                    entry_reason_text = f"opened long when monthly filter is on and rsi is lower than: {rsi_long_open_monthly_profit}\n"
                                    entry_reason_text += generate_entry_reason_text(trade_id=next_trade_id, updates=updates)
                                    long_open_reasons[i] = entry_reason_text
                            
                            next_trade_id += 1
                            # record which cross enabled this trade and init trailing state
                            last_trade_cross_index = last_cross_index
                            updates = None

                # ==== RSI OPEN SHORT ====
                if rsi_trade_monthly_filter_on:

                    momentum_down = (
                        close_prices[i] < close_prices[i-1]
                        and close_prices[i-1] < close_prices[i-2]
                    )

                    highest_rsi_last_n = max(rsi_list[i - highest_rsi_last_n_value : i])

                    rsi_now = rsi_list[i]
                    rsi_prev = rsi_list[i-1]

                    rsi_rejection_down = rsi_prev > rsi_now

                    rsi_distance_down = highest_rsi_last_n - rsi_now

                    if rsi_in_cooldown:
                        if i > rsi_last_index_stop_loss_bar + rsi_cooldown_bars:
                            rsi_in_cooldown = False

                    if (
                        highest_rsi_last_n >= rsi_short_open_monthly_profit
                        and rsi_now >= max(0, rsi_short_open_monthly_profit - rsi_entry_buffer)
                        and rsi_rejection_down
                        and rsi_distance_down >= rsi_distance_threshold
                        and momentum_down
                        and len(open_positions) < rsi_max_open_trades
                        and not rsi_in_cooldown
                    ):
                        # ---- open short ----
                        updates = trade_manager.open_short(
                            i,
                            close_prices,
                            close_times,
                            balance,
                            balance_without_fee,
                            rsi_trade_amount_percent,
                            balance + sum(p['margin'] for p in open_positions),
                            balance_without_fee + sum(p['margin_no_fee'] for p in open_positions),
                            tactical_balance,
                            leverage = rsi_leverage,)
                        if updates is not None:
                            
                            balance = updates['balance']
                            balance_without_fee = updates['balance_without_fee']
                            trade_reason = 'rsi_ma_strategy'
                            position = {
                                'trade_id': f"{trade_reason}_{next_trade_id:04d}",
                                'side': "short",
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
                                'trade_amount_percent': updates['trade_amount_percent'],
                                'leverage': updates['leverage'],
                                'open_time_value': updates['open_time_value'],
                                'target_close_price_loss': updates['entry_price'],
                                'reason': trade_reason
                            }
                            open_positions.append(position)
                            
                            # open point on chart
                            if short_open_points is not None:
                                short_open_points.append((i, position['entry_price']))
                                # open reason text
                                if short_open_reasons is not None:
                                    # default texts
                                    entry_reason_text = f"opened short when monthly filter is on and rsi is upper than: {rsi_short_open_monthly_profit}\n"
                                    entry_reason_text += generate_entry_reason_text(trade_id=next_trade_id, updates=updates)
                                    short_open_reasons[i] = entry_reason_text

                            next_trade_id += 1
                            # record which cross enabled this trade and init trailing state
                            last_trade_cross_index = last_cross_index
                            updates = None


                if len([p for p in open_positions if p['reason'] != "rsi_ma_strategy"]) == 0:
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



        # ===================== OPEN LONG =====================
        # Require that EMA/MA50 have crossed and the last cross was bullish,
        # and avoid opening multiple trades for the same cross.
        if len(open_positions) < max_open_trades and _count_open("short") == 0 and _count_open("long") == 0 and i >= cooldown_until_index:
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

                # ---- Positive Scores ----
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
                # ---- Negative Scores (late-entry guard)
                # 1) only penalize when a sharp move already happened AND price is overextended AND momentum is cooling
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
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
                        if verbose:
                            print(f"⏭️ SKIP LONG | skips left: {skip_trades_left}")
                        continue
                    entry_reason_text = build_score_reason_text(
                        "LONG ENTRY SCORE REASONS",
                        entry_reasons,
                        entry_score,
                        entry_score_threshold,
                    )

                    # ---- open long ----
                    updates = trade_manager.open_long(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        trade_amount_percent,
                        balance + sum(p['margin'] for p in open_positions),
                        balance_without_fee + sum(p['margin_no_fee'] for p in open_positions),
                        tactical_balance)
                    if updates is not None:

                        balance = updates['balance']
                        balance_without_fee = updates['balance_without_fee']
                        trade_reason = 'ma_strategy'
                        position = {
                            'trade_id': f"{trade_reason}_{next_trade_id:04d}",
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
                            'trade_amount_percent': updates['trade_amount_percent'],
                            'leverage': updates['leverage'],
                            'open_time_value': updates['open_time_value'],
                            'target_close_price_loss': updates['entry_price'],
                            'reason': trade_reason
                        }
                        open_positions.append(position)
                        
                        # open point on chart
                        if long_open_points is not None:
                            long_open_points.append((i, position['entry_price']))
                            # open reason text
                            if long_open_reasons is not None:
                                # default texts
                                entry_reason_text += generate_entry_reason_text(trade_id=next_trade_id, updates=updates)
                                long_open_reasons[i] = entry_reason_text
                        
                        next_trade_id += 1
                        # record which cross enabled this trade and init trailing state
                        last_trade_cross_index = last_cross_index
                        updates = None

        # ===================== SCALE ENTRY LONG =====================
        if scale_in_enabled and len(open_positions) < max_open_trades and _count_open("short") == 0 and _count_open("long") > 0 and i >= cooldown_until_index:
            first_long_position = min(
                (p for p in open_positions if p['side'] == "long"),
                key=lambda x: x['entry_index'],
                default=None
            )
            if first_long_position is not None:
                first_long_entry_price = first_long_position['entry_price']
                long_scale_entry_profit_trigger_price = first_long_entry_price * (1 + scale_entry_profit_trigger_pct)
                long_scale_entry_loss_trigger_price = first_long_entry_price * (1 - scale_entry_loss_trigger_pct)
                long_scale_entry_reason = None
                if scale_entry_on_profit_enabled and close_prices[i] >= long_scale_entry_profit_trigger_price:
                    long_scale_entry_reason = "profit"
                elif scale_entry_on_loss_enabled and close_prices[i] <= long_scale_entry_loss_trigger_price:
                    long_scale_entry_reason = "loss"

                # count number of scales
                if long_scale_entry_reason == "profit":
                    long_profit_scale_entry_attempts += 1
                elif long_scale_entry_reason == "loss":
                    long_loss_scale_entry_attempts += 1

                long_profit_scale_entry_score = 0
                if long_scale_entry_reason == "profit" and profit_scale_entry_filter_enabled:
                    # validate profit scale entry quality before adding to a winning position.
                    if ema_16[i] > ma_50[i]:
                        long_profit_scale_entry_score += 1
                    if ma_100[i] > ma_200[i]:
                        long_profit_scale_entry_score += 1
                    if i > 0 and close_prices[i] > open_prices[i] and close_prices[i] > close_prices[i - 1]:
                        long_profit_scale_entry_score += 1
                    if atr[i] is not None and atr_ma[i] is not None and atr_ma[i] > 0:
                        long_scale_entry_atr_ratio = atr[i] / atr_ma[i]
                        if long_scale_entry_atr_ratio >= profit_scale_entry_atr_ratio_min:
                            long_profit_scale_entry_score += 1
                    if volume_filter:
                        vol_now = volume_prices[i]
                        vol_avg15 = vol_avg_15_list[i]
                        if vol_now >= volume_spike_multiplier * vol_avg15:
                            long_profit_scale_entry_score += 2
                    if long_profit_scale_entry_score < profit_scale_entry_min_score:
                        long_filtered_profit_scale_entries += 1
                        long_scale_entry_reason = None

                if long_scale_entry_reason is not None:
                    updates = trade_manager.open_long(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        scale_entry_amount_percent,
                        balance + sum(p['margin'] for p in open_positions),
                        balance_without_fee + sum(p['margin_no_fee'] for p in open_positions),
                        tactical_balance)
                    if updates is not None:

                        # count profits, losses Scales
                        if long_scale_entry_reason == "profit":
                            long_profit_scale_entries += 1
                        elif long_scale_entry_reason == "loss":
                            long_loss_scale_entries += 1
                        
                        # ==== UPDATE ====
                        balance = updates['balance']
                        balance_without_fee = updates['balance_without_fee']
                        trade_reason = 'scale_ma_strategy'
                        position = {
                            'trade_id': f"{trade_reason}_{next_trade_id:04d}",
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
                            'trade_amount_percent': updates['trade_amount_percent'],
                            'leverage': updates['leverage'],
                            'open_time_value': updates['open_time_value'],
                            'target_close_price_loss': updates['entry_price'],
                            'reason': trade_reason
                        }
                        open_positions.append(position)
                        next_trade_id += 1
                        if long_open_points is not None:
                            long_open_points.append((i, position['entry_price']))
                            if long_open_reasons is not None:
                                long_scale_entry_text = (
                                    f"LONG SCALE ENTRY\n"
                                    f"Order size: {scale_entry_amount_percent*100:.2f}%\n"
                                )
                                if long_scale_entry_reason == "profit":
                                    long_scale_entry_text += (
                                        f"Price moved +{scale_entry_profit_trigger_pct*100:.2f}% from first LONG entry."
                                    )

                                    if profit_scale_entry_filter_enabled:
                                        long_scale_entry_text += (
                                            f"\nProfit filter score: {long_profit_scale_entry_score}/{profit_scale_entry_min_score}"
                                        )

                                long_open_reasons[i] = long_scale_entry_text
                                
                    updates = None


        # ===================== CLOSE LONG =====================
        close_all_longs = False
        long_exit_reason_text = None
        for p in open_positions[:]:
            if p['side'] != "long":
                continue
            exit_score = 0
            exit_reasons = []
            entry_price = p['entry_price']

            if p['highest_since_entry'] is None:
                p['highest_since_entry'] = entry_price
            if high_prices[i] > p['highest_since_entry']:
                p['highest_since_entry'] = high_prices[i]

            # ---- Positive Scores ----
            # 1) LOSS GUARD (based on dynamic loss-lock line)
            if p['target_close_price_loss'] is not None:
                loss_pct = (p['target_close_price_loss'] - close_prices[i]) / p['target_close_price_loss']
                if loss_pct >= loss_exit_pct_2:
                    exit_score += exit_score_loss_guard_2
                    exit_reasons.append((f"Loss guard triggered ({loss_exit_pct_2*100:.0f}%+ loss)", exit_score_loss_guard_2))
                if loss_pct >= loss_exit_pct_1:
                    exit_score += exit_score_loss_guard_1
                    exit_reasons.append((f"Loss guard triggered ({loss_exit_pct_1*100:.0f}%+ loss)", exit_score_loss_guard_1))

            # 2) PROFIT GUARD
            profit_pct = (close_prices[i] - entry_price) / entry_price
            if profit_pct >= profit_exit_pct_2:
                exit_score += exit_score_profit_guard_2
                exit_reasons.append((f"Profit guard triggered ({profit_exit_pct_2*100:.0f}%+ profit)", exit_score_profit_guard_2))
            if profit_pct >= profit_exit_pct_1:
                exit_score += exit_score_profit_guard_1
                exit_reasons.append((f"Profit guard triggered ({profit_exit_pct_1*100:.0f}%+ profit)", exit_score_profit_guard_1))

            # 3) EMA SLOPE WEAKNESS
            if i - slope_window >= 0 and ema_16[i] < ema_16[i - slope_window]:
                exit_score += exit_score_ema_slope
                exit_reasons.append(("EMA16 slope weakness", exit_score_ema_slope))
            # 4) EMA16 CROSSED BELOW MA50
            if ema_16[i] < ma_50[i]:
                exit_score += exit_score_ema_cross
                exit_reasons.append(("EMA16 crossed below MA50", exit_score_ema_cross))
            # 5) MA TREND WEAKNESS (MA100 < MA200)
            if ma_100[i] < ma_200[i]:
                exit_score += exit_score_ma_trend
                exit_reasons.append(("MA100 below MA200", exit_score_ma_trend))

            # 6) TRAILING RETRACE EXIT
            if p['entry_index'] is not None and i > p['entry_index']:
                if p['highest_since_entry'] >= entry_price * (1 + trail_activate_pct):
                    if close_prices[i] <= p['highest_since_entry'] * (1 - trail_retrace_pct):
                        exit_score += exit_score_trailing
                        exit_reasons.append(("Trailing retrace exit", exit_score_trailing))

            # 7) ADX WEAKENING EXIT
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += exit_score_adx
                            exit_reasons.append(("ADX weakening", exit_score_adx))

            # 8) STRONG OPPOSITE CANDLE
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] < open_prices[i]:
                    body = open_prices[i] - close_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += exit_score_opposite_candle
                        exit_reasons.append(("Strong opposite bearish candle", exit_score_opposite_candle))

            # Negative Scores:
            # 1) POST-CROSS SHARP-MOVE PENALTY
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
                    exit_reasons.append((penalty_reason_text, -post_cross_penalty_score))
                    if penalty_long_points is not None:
                        penalty_long_points.append((i, close_prices[i]))
                        if penalty_long_reasons is not None:
                            penalty_long_reasons[i] = (
                                f"LONG penalty marker\n{penalty_reason_text}\nScore impact: -{post_cross_penalty_score}"
                            )

            if exit_score >= exit_score_threshold:
                long_exit_reason_text = build_score_reason_text(
                    "LONG EXIT SCORE REASONS",
                    exit_reasons,
                    exit_score,
                    exit_score_threshold,
                )
                close_all_longs = True
                break

        if close_all_longs:
            long_positions_to_close = [p for p in open_positions[:] if p['side'] == "long"]
            for p in long_positions_to_close:
                remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                remaining_open_margin_no_fee = sum(x['margin_no_fee'] for x in open_positions if x is not p)
                # remaining_open_equity = _open_positions_equity(close_prices[i], p)
                close_price = close_prices[i]
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
                    p['trade_amount_percent'],
                    profit_percent_per_month,
                    save_money,
                    trade_power,
                    p['trade_id'],
                    remaining_open_margin,
                    remaining_open_margin_no_fee,
                    tactical_balance,
                    p['reason'],
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    p['balance_before_trade'],
                    p['balance_before_trade_no_fee'],
                    remaining_open_equity=remaining_open_margin)
                
                # count profit,loss scales positions
                if p.get('reason') == 'scale_ma_strategy':
                    scale_ma_long_total += 1
                    scale_ma_long_total_profit += updates['profit']

                    if updates['profit'] > 0:
                        scale_ma_long_wins += 1
                    else:
                        scale_ma_long_losses += 1

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
                    long_close_points.append((i, close_price))
                    # close reason text
                    if long_close_reasons is not None:
                        long_exit_reason_text += generate_close_reason_text(trade_id=p['trade_id'], updates=updates)
                        if len(long_positions_to_close) > 1:
                            long_close_reasons[i] = f"\n{long_exit_reason_text}\nBatch close: all open LONG positions closed together."
                        else:
                            long_close_reasons[i] = long_exit_reason_text
                
                updates = None

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
                        if balance >= tactical_balance + (tactical_balance * monthly_compound / 100):
                            tactical_balance = tactical_balance + (tactical_balance * monthly_compound / 100)
                        else:
                            tactical_balance = balance
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

        # ===================== OPEN SHORT =====================
        # Require that EMA/MA50 have crossed and the last cross was bearish,
        # and avoid opening multiple trades for the same cross.
        if len(open_positions) < max_open_trades and _count_open("long") == 0 and _count_open("short") == 0 and i >= cooldown_until_index:
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
                # ---- Positive Scores
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
                # ---- Negative Scores (late-entry guard)
                # 1) only penalize when a sharp move already happened AND price is overextended AND momentum is cooling
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
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
                        if verbose:
                            print(f"⏭️ SKIP SHORT | skips left: {skip_trades_left}")
                        continue
                    entry_reason_text = build_score_reason_text(
                        "SHORT ENTRY SCORE REASONS",
                        entry_reasons,
                        entry_score,
                        entry_score_threshold,
                    )

                    # ---- open short ----
                    updates = trade_manager.open_short(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        trade_amount_percent,
                        balance + sum(p['margin'] for p in open_positions),
                        balance_without_fee + sum(p['margin_no_fee'] for p in open_positions),
                        tactical_balance)
                    if updates is not None:
                        
                        balance = updates['balance']
                        balance_without_fee = updates['balance_without_fee']
                        trade_reason = 'ma_strategy'
                        position = {
                            'trade_id': f"{trade_reason}_{next_trade_id:04d}",
                            'side': "short",
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
                            'trade_amount_percent': updates['trade_amount_percent'],
                            'leverage': updates['leverage'],
                            'open_time_value': updates['open_time_value'],
                            'target_close_price_loss': updates['entry_price'],
                            'reason': trade_reason
                        }
                        open_positions.append(position)
                        
                        # open point on chart
                        if short_open_points is not None:
                            short_open_points.append((i, position['entry_price']))
                            # open reason text
                            if short_open_reasons is not None:
                                # default texts
                                entry_reason_text += generate_entry_reason_text(trade_id=next_trade_id, updates=updates)
                                short_open_reasons[i] = entry_reason_text

                        next_trade_id += 1
                        # record which cross enabled this trade and init trailing state
                        last_trade_cross_index = last_cross_index
                        updates = None

        # ===================== SCALE ENTRY SHORT =====================
        if scale_in_enabled and len(open_positions) < max_open_trades and _count_open("long") == 0 and _count_open("short") > 0 and i >= cooldown_until_index:
            first_short_position = min(
                (p for p in open_positions if p['side'] == "short"),
                key=lambda x: x['entry_index'],
                default=None
            )
            if first_short_position is not None:
                first_short_entry_price = first_short_position['entry_price']
                short_scale_entry_profit_trigger_price = first_short_entry_price * (1 - scale_entry_profit_trigger_pct)
                short_scale_entry_loss_trigger_price = first_short_entry_price * (1 + scale_entry_loss_trigger_pct)
                short_scale_entry_reason = None
                if scale_entry_on_profit_enabled and close_prices[i] <= short_scale_entry_profit_trigger_price:
                    short_scale_entry_reason = "profit"
                elif scale_entry_on_loss_enabled and close_prices[i] >= short_scale_entry_loss_trigger_price:
                    short_scale_entry_reason = "loss"

                # count scales
                if short_scale_entry_reason == "profit":
                    short_profit_scale_entry_attempts += 1
                elif short_scale_entry_reason == "loss":
                    short_loss_scale_entry_attempts += 1

                short_profit_scale_entry_score = 0
                if short_scale_entry_reason == "profit" and profit_scale_entry_filter_enabled:
                    # validate profit scale entry quality before adding to a winning SHORT position.
                    if ema_16[i] < ma_50[i]:
                        short_profit_scale_entry_score += 1
                    if ma_100[i] < ma_200[i]:
                        short_profit_scale_entry_score += 1
                    if i > 0 and close_prices[i] < open_prices[i] and close_prices[i] < close_prices[i - 1]:
                        short_profit_scale_entry_score += 1
                    if atr[i] is not None and atr_ma[i] is not None and atr_ma[i] > 0:
                        short_scale_entry_atr_ratio = atr[i] / atr_ma[i]
                        if short_scale_entry_atr_ratio >= profit_scale_entry_atr_ratio_min:
                            short_profit_scale_entry_score += 1
                    if volume_filter:
                        vol_now = volume_prices[i]
                        vol_avg15 = vol_avg_15_list[i]
                        if vol_now >= volume_spike_multiplier * vol_avg15:
                            short_profit_scale_entry_score += 2
                    if short_profit_scale_entry_score < profit_scale_entry_min_score:
                        short_filtered_profit_scale_entries += 1
                        short_scale_entry_reason = None

                if short_scale_entry_reason is not None:
                    updates = trade_manager.open_short(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        scale_entry_amount_percent,
                        balance + sum(p['margin'] for p in open_positions),
                        balance_without_fee + sum(p['margin_no_fee'] for p in open_positions),
                        tactical_balance)
                    if updates is not None:
                        
                        # count profits, losses Scales
                        if short_scale_entry_reason == "profit":
                            short_profit_scale_entries += 1
                        elif short_scale_entry_reason == "loss":
                            short_loss_scale_entries += 1

                        # === UPDATE ===
                        balance = updates['balance']
                        balance_without_fee = updates['balance_without_fee']
                        trade_reason = 'scale_ma_strategy'
                        position = {
                            'trade_id': f"{trade_reason}_{next_trade_id:04d}",
                            'side': "short",
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
                            'trade_amount_percent': updates['trade_amount_percent'],
                            'leverage': updates['leverage'],
                            'open_time_value': updates['open_time_value'],
                            'target_close_price_loss': updates['entry_price'],
                            'reason': trade_reason
                        }
                        open_positions.append(position)
                        next_trade_id += 1
                        if short_open_points is not None:
                            short_open_points.append((i, position['entry_price']))
                            if short_open_reasons is not None:
                                short_scale_entry_text = (
                                    f"SHORT SCALE ENTRY\n"
                                    f"Order size: {scale_entry_amount_percent*100:.2f}%\n"
                                )
                                if short_scale_entry_reason == "profit":
                                    short_scale_entry_text += (
                                        f"Price moved -{scale_entry_profit_trigger_pct*100:.2f}% from first SHORT entry."
                                    )

                                    if profit_scale_entry_filter_enabled:
                                        short_scale_entry_text += (
                                            f"\nProfit filter score: {short_profit_scale_entry_score}/{profit_scale_entry_min_score}"
                                        )

                                short_open_reasons[i] = short_scale_entry_text

                    updates = None


        # ===================== CLOSE SHORT =====================
        close_all_shorts = False
        short_exit_reason_text = None
        for p in open_positions[:]:
            if p['side'] != "short":
                continue
            exit_score = 0
            exit_reasons = []
            entry_price = p['entry_price']

            if p['lowest_since_entry'] is None:
                p['lowest_since_entry'] = entry_price
            if low_prices[i] < p['lowest_since_entry']:
                p['lowest_since_entry'] = low_prices[i]

            # 1) LOSS GUARD (based on dynamic loss-lock line)
            if p['target_close_price_loss'] is not None:
                loss_pct = (close_prices[i] - p['target_close_price_loss']) / p['target_close_price_loss']
                if loss_pct >= loss_exit_pct_2:
                    exit_score += exit_score_loss_guard_2
                    exit_reasons.append((f"Loss guard triggered ({loss_exit_pct_2*100:.0f}%+ loss)", exit_score_loss_guard_2))
                if loss_pct >= loss_exit_pct_1:
                    exit_score += exit_score_loss_guard_1
                    exit_reasons.append((f"Loss guard triggered ({loss_exit_pct_1*100:.0f}%+ loss)", exit_score_loss_guard_1))

            # 2) PROFIT GUARD
            profit_pct = (entry_price - close_prices[i]) / entry_price
            if profit_pct >= profit_exit_pct_2:
                exit_score += exit_score_profit_guard_2
                exit_reasons.append((f"Profit guard triggered ({profit_exit_pct_2*100:.0f}%+ profit)", exit_score_profit_guard_2))
            if profit_pct >= profit_exit_pct_1:
                exit_score += exit_score_profit_guard_1
                exit_reasons.append((f"Profit guard triggered ({profit_exit_pct_1*100:.0f}%+ profit)", exit_score_profit_guard_1))

            # 3) EMA SLOPE WEAKNESS (SHORT CONTEXT)
            if i - slope_window >= 0 and ema_16[i] > ema_16[i - slope_window]:
                exit_score += exit_score_ema_slope
                exit_reasons.append(("EMA16 slope weakness (short)", exit_score_ema_slope))
            # 4) EMA16 CROSSED ABOVE MA50
            if ema_16[i] > ma_50[i]:
                exit_score += exit_score_ema_cross
                exit_reasons.append(("EMA16 crossed above MA50", exit_score_ema_cross))
            # 5) MA TREND WEAKNESS (MA100 >= MA200 for short)
            if ma_100[i] >= ma_200[i]:
                exit_score += exit_score_ma_trend
                exit_reasons.append(("MA100 above/equal MA200", exit_score_ma_trend))

            # 6) TRAILING RETRACE EXIT
            if p['entry_index'] is not None and i > p['entry_index']:
                if p['lowest_since_entry'] <= entry_price * (1 - trail_activate_pct):
                    if close_prices[i] >= p['lowest_since_entry'] * (1 + trail_retrace_pct):
                        exit_score += exit_score_trailing
                        exit_reasons.append(("Trailing retrace exit", exit_score_trailing))

            # 7) ADX WEAKENING EXIT
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += exit_score_adx
                            exit_reasons.append(("ADX weakening", exit_score_adx))

            # 8) STRONG OPPOSITE CANDLE
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] > open_prices[i]:
                    body = close_prices[i] - open_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += exit_score_opposite_candle
                        exit_reasons.append(("Strong opposite bullish candle", exit_score_opposite_candle))

            # Negative Scores:
            # 1) POST-CROSS SHARP-MOVE PENALTY
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
                    exit_reasons.append((penalty_reason_text, -post_cross_penalty_score))
                    if penalty_short_points is not None:
                        penalty_short_points.append((i, close_prices[i]))
                        if penalty_short_reasons is not None:
                            penalty_short_reasons[i] = (
                                f"SHORT penalty marker\n{penalty_reason_text}\nScore impact: -{post_cross_penalty_score}"
                            )

            if exit_score >= exit_score_threshold:
                short_exit_reason_text = build_score_reason_text(
                    "SHORT EXIT SCORE REASONS",
                    exit_reasons,
                    exit_score,
                    exit_score_threshold,
                )
                close_all_shorts = True
                break

        if close_all_shorts:
            short_positions_to_close = [p for p in open_positions[:] if p['side'] == "short"]
            for p in short_positions_to_close:
                remaining_open_margin = sum(x['margin'] for x in open_positions if x is not p)
                remaining_open_margin_no_fee = sum(x['margin_no_fee'] for x in open_positions if x is not p)
                # remaining_open_equity = _open_positions_equity(close_prices[i], p)
                close_price = close_prices[i]
                updates = trade_manager.close_short(
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
                    total_wins_short,
                    total_losses,
                    total_short,
                    cooldown_after_big_pnl,
                    p['leverage'],
                    cooldown_until_index,
                    p['open_time_value'],
                    csv_logger,
                    p['trade_amount_percent'],
                    profit_percent_per_month,
                    save_money,
                    trade_power,
                    p['trade_id'],
                    remaining_open_margin,
                    remaining_open_margin_no_fee,
                    tactical_balance,
                    p['reason'],
                    balance_before_close_batch,
                    balance_before_close_batch_no_fee,
                    p['balance_before_trade'],
                    p['balance_before_trade_no_fee'],
                    remaining_open_equity=remaining_open_margin
                    )

                # count profit,loss scales positions
                if p.get('reason') == 'scale_ma_strategy':
                    scale_ma_short_total += 1
                    scale_ma_short_total_profit += updates['profit']

                    if updates['profit'] > 0:
                        scale_ma_short_wins += 1
                    else:
                        scale_ma_short_losses += 1

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
                profit_percent_per_month = updates['profit_percent_per_month']
                save_money = updates['save_money']
                trade_power = updates['trade_power']
                # remove position
                open_positions.remove(p)

                # close point on chart
                if short_close_points is not None:
                    short_close_points.append((i, close_price))
                    # close reason text
                    if short_close_reasons is not None:
                        short_exit_reason_text += generate_close_reason_text(trade_id=p['trade_id'], updates=updates)
                        if len(short_positions_to_close) > 1:
                            short_close_reasons[i] = f"\n{short_exit_reason_text}\nBatch close: all open SHORT positions closed together."
                        else:
                            short_close_reasons[i] = short_exit_reason_text

                updates = None

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
                        if balance >= tactical_balance + (tactical_balance * monthly_compound / 100):
                            tactical_balance = tactical_balance + (tactical_balance * monthly_compound / 100)
                        else:
                            tactical_balance = balance
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


    # ====== scale calculation ======
    # ---- LONG ----
    scale_long_total = scale_ma_long_wins + scale_ma_long_losses

    scale_long_winrate = (
        round(scale_ma_long_wins / scale_long_total * 100, 2)
        if scale_long_total > 0 else 0
    )

    # ---- SHORT ----
    scale_short_total = scale_ma_short_wins + scale_ma_short_losses

    short_winrate = (
        round(scale_ma_short_wins / scale_short_total * 100, 2)
        if scale_short_total > 0 else 0
    )

    # ---- OVERALL ----
    scale_total_profit_closed = scale_ma_long_wins + scale_ma_short_wins
    scale_total_loss_closed = scale_ma_long_losses + scale_ma_short_losses

    scale_total_closed = scale_total_profit_closed + scale_total_loss_closed

    scale_total_winrate = (
        round(scale_total_profit_closed / scale_total_closed * 100, 2)
        if scale_total_closed > 0 else 0
    )

    scale_total_profit_amount = (
        scale_ma_long_total_profit +
        scale_ma_short_total_profit
    )

    # ====== RSI calculation OVERALL ======
    rsi_total_trades = rsi_long_total + rsi_short_total
    rsi_total_wins = rsi_long_wins + rsi_short_wins
    rsi_total_losses = rsi_long_losses + rsi_short_losses
    rsi_total_profit = rsi_long_total_profit + rsi_short_total_profit
    rsi_winrate = round(rsi_total_wins / rsi_total_trades * 100, 2) if rsi_total_trades > 0 else 0

    if monthly_stop_reasons:
        profit_months_count = sum(1 for r in monthly_stop_reasons if r == "profit")
        loss_months_count = sum(1 for r in monthly_stop_reasons if r == "loss")
    else:
        # fallback: keep previous behavior when no explicit monthly stop reason exists
        profit_months_count = sum(1 for p in lst_profit_percent_per_month if p > 0)
        loss_months_count = sum(1 for p in lst_profit_percent_per_month if p < 0)


    # =========================
    # NORMALIZED STRATEGY SCORE
    # =========================

    final_balance = total_money_static

    # --- Growth ---
    growth = final_balance / first_balance

    # --- Risk (Drawdown) ---
    risk = abs(max_drawdown) / 100

    # --- Consistency ---
    consistency = profit_months_count / max(1, (profit_months_count + loss_months_count))

    # --- Quality (Winrate) ---
    quality = win_rate / 100

    # =========================
    # FINAL SCORE
    # =========================
    score = (
        (growth ** 1.15)
        * (0.6 + quality)
        * (0.5 + consistency)
        / (1 + (risk * 2))
    )

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
        print("Total score:", score)


        # SCALE ENTRY REPORT
        print("\n================ SCALE ENTRY REPORT ================\n")

        # ---- LONG ENTRY ----
        print("===== LONG SCALE ENTRY =====")
        print(f"Profit Triggered : {long_profit_scale_entry_attempts}")
        print(f"Profit Executed  : {long_profit_scale_entries}")
        print(f"Profit Filtered  : {long_filtered_profit_scale_entries}")
        print()
        print(f"Loss Triggered   : {long_loss_scale_entry_attempts}")
        print(f"Loss Executed    : {long_loss_scale_entries}")

        print("\n-----------------------------------------------------\n")

        # ---- SHORT ENTRY ----
        print("===== SHORT SCALE ENTRY =====")
        print(f"Profit Triggered : {short_profit_scale_entry_attempts}")
        print(f"Profit Executed  : {short_profit_scale_entries}")
        print(f"Profit Filtered  : {short_filtered_profit_scale_entries}")
        print()
        print(f"Loss Triggered   : {short_loss_scale_entry_attempts}")
        print(f"Loss Executed    : {short_loss_scale_entries}")

        print("\n=====================================================\n")


        print("================ SCALE PERFORMANCE =================\n")

        # ---- LONG PERFORMANCE ----
        print("===== LONG SCALE STATS =====")
        print(f"Total Closed : {scale_long_total}")
        print(f"Wins         : {scale_ma_long_wins}")
        print(f"Losses       : {scale_ma_long_losses}")
        print(f"Winrate      : {scale_long_winrate}%")
        print(f"Total Profit : {round(scale_ma_long_total_profit, 2)}")

        print("\n-----------------------------------------------------\n")

        # ---- SHORT PERFORMANCE ----
        print("===== SHORT SCALE STATS =====")
        print(f"Total Closed : {scale_short_total}")
        print(f"Wins         : {scale_ma_short_wins}")
        print(f"Losses       : {scale_ma_short_losses}")
        print(f"Winrate      : {short_winrate}%")
        print(f"Total Profit : {round(scale_ma_short_total_profit, 2)}")

        print("\n-----------------------------------------------------\n")

        # ---- OVERALL PERFORMANCE ----
        print("===== OVERALL SCALE PERFORMANCE =====")
        print(f"Total Trades : {scale_total_closed}")
        print(f"Wins         : {scale_total_profit_closed}")
        print(f"Losses       : {scale_total_loss_closed}")
        print(f"Winrate      : {scale_total_winrate}%")
        print(f"Total Profit : {round(scale_total_profit_amount, 2)}")

        print("\n=====================================================\n")


        # ======== RSI STRATEGY REPORT ========
        print("\n================ RSI STRATEGY REPORT ================\n")

        # ---- LONG ----
        print("===== RSI LONG STATS =====")
        print("Total:", rsi_long_total)
        print("Wins:", rsi_long_wins)
        print("Losses:", rsi_long_losses)

        if rsi_long_total > 0:
            print("Winrate:", round(rsi_long_wins / rsi_long_total * 100, 2), "%")

        print("Total Profit:", round(rsi_long_total_profit, 2))
        print("\n")

        # ---- SHORT ----
        print("===== RSI SHORT STATS =====")
        print("Total:", rsi_short_total)
        print("Wins:", rsi_short_wins)
        print("Losses:", rsi_short_losses)

        if rsi_short_total > 0:
            print("Winrate:", round(rsi_short_wins / rsi_short_total * 100, 2), "%")

        print("Total Profit:", round(rsi_short_total_profit, 2))
        print("\n-----------------------------------------------------\n")


        print("===== OVERALL RSI PERFORMANCE =====")
        print("Total Trades:", rsi_total_trades)
        print("Wins:", rsi_total_wins)
        print("Losses:", rsi_total_losses)

        if rsi_total_trades > 0:
            print("Winrate:", rsi_winrate, "%")

        print("Total Profit:", round(rsi_total_profit, 2))
        print("\n=====================================================\n")


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
        # ==== all results ====
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
        "loss_months": loss_months_count,

        # score
        'score': score,

        # ==== RSI RESULTS TOTAL ====
        "rsi_total_trades": rsi_total_trades,
        "rsi_wins": rsi_total_wins,
        "rsi_losses": rsi_total_losses,
        "rsi_winrate": rsi_winrate,
        "rsi_total_profit": rsi_total_profit,
        # RSI LONG
        "rsi_long_trades": rsi_long_total,
        "rsi_long_wins": rsi_long_wins,
        "rsi_long_losses": rsi_long_losses,
        "rsi_long_winrate": round(rsi_long_wins / rsi_long_total * 100, 2) if rsi_long_total > 0 else 0,
        "rsi_long_profit": rsi_long_total_profit,
        # RSI SHORT
        "rsi_short_trades": rsi_short_total,
        "rsi_short_wins": rsi_short_wins,
        "rsi_short_losses": rsi_short_losses,
        "rsi_short_winrate": round(rsi_short_wins / rsi_short_total * 100, 2) if rsi_short_total > 0 else 0,
        "rsi_short_profit": rsi_short_total_profit,

        # ==== SCALE RESULTS TOTAL ====
        "scale_total_trades": scale_total_closed,
        "scale_wins": scale_total_profit_closed,
        "scale_losses": scale_total_loss_closed,
        "scale_winrate": scale_total_winrate,
        "scale_total_profit": scale_total_profit_amount,
        # SCALE LONG
        "scale_long_trades": scale_long_total,
        "scale_long_wins": scale_ma_long_wins,
        "scale_long_losses": scale_ma_long_losses,
        "scale_long_winrate": scale_long_winrate,
        "scale_long_profit": scale_ma_long_total_profit,
        # SCALE SHORT
        "scale_short_trades": scale_short_total,
        "scale_short_wins": scale_ma_short_wins,
        "scale_short_losses": scale_ma_short_losses,
        "scale_short_winrate": short_winrate,
        "scale_short_profit": scale_ma_short_total_profit,
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
