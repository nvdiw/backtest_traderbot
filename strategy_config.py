from dataclasses import dataclass, fields


def _coerce_like(current_value, new_value):
    if isinstance(current_value, bool):
        if isinstance(new_value, str):
            return new_value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(new_value)
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        return int(new_value)
    if isinstance(current_value, float):
        return float(new_value)
    return new_value


def _apply_common_tune(config, tune):
    if not tune:
        return config

    field_names = {field.name for field in fields(config)}
    for key, value in tune.items():
        if key in field_names:
            setattr(config, key, _coerce_like(getattr(config, key), value))

    # Backward-compatible tune aliases used by optimize.py and older runs.
    if 'trade_amount_percent_neworder' in tune:
        config.scale_entry_amount_percent = float(tune['trade_amount_percent_neworder'])

    if 'scale_entry_trigger_pct' in tune:
        trigger_pct = float(tune['scale_entry_trigger_pct'])
        config.scale_entry_profit_trigger_pct = trigger_pct
        config.scale_entry_loss_trigger_pct = trigger_pct
    elif 'scale_in_trigger_move_pct' in tune:
        trigger_pct = float(tune['scale_in_trigger_move_pct'])
        config.scale_entry_profit_trigger_pct = trigger_pct
        config.scale_entry_loss_trigger_pct = trigger_pct

    if 'loss_scale_entry_long_atr_ratio_min' in tune:
        config.loss_scale_entry_atr_ratio_min = float(tune['loss_scale_entry_long_atr_ratio_min'])
    if 'loss_scale_entry_short_atr_ratio_min' in tune:
        config.loss_scale_entry_atr_ratio_min = float(tune['loss_scale_entry_short_atr_ratio_min'])

    if 'ema_16' in tune:
        config.ema_16_period = int(tune['ema_16'])
    if 'ma_50' in tune:
        config.ma_50_period = int(tune['ma_50'])
    if 'ma_100' in tune:
        config.ma_100_period = int(tune['ma_100'])
    if 'ma_200' in tune:
        config.ma_200_period = int(tune['ma_200'])

    config.max_open_trades = max(1, int(config.max_open_trades))

    return config


@dataclass
class BaseStrategyConfig:
    # Capital and position sizing
    balance: float = 1000
    leverage: float = 10
    trade_amount_percent: float = 0.5
    scale_entry_amount_percent: float = 0.2
    scale_entry_profit_trigger_pct: float = 0.039
    scale_entry_loss_trigger_pct: float = 0.03
    save_money: float = 0

    # Safe leverage
    safe_leverage_low: float = 2
    safe_leverage_med: float = 3
    safe_leverage_high: float = 4
    safe_leverage_balance_pct_low: float = 80
    safe_leverage_balance_pct_med: float = 80
    safe_leverage_balance_pct_high: float = 90
    save_money_recover_trigger_pct: float = 75

    # Monthly control
    monthly_profit_percent_stop_trade: int = 8
    monthly_loss_percent_stop_trade: int = 19
    monthly_compound: float = 3
    monthly_profit_close_filter: bool = True
    monthly_loss_close_filter: bool = False

    # Scale entry controls
    scale_entry_on_profit_enabled: bool = True
    scale_entry_on_loss_enabled: bool = False
    scale_in_enabled: bool = True
    loss_scale_entry_filter_enabled: bool = True
    loss_scale_entry_min_score: int = 2
    loss_scale_entry_atr_ratio_min: float = 1.0

    # Filters and behavior switches
    adx_filter: bool = True
    volume_filter: bool = True
    atr_filter: bool = True
    consecutive_losses_month_stop_filter: bool = False
    skip_logic: bool = False
    max_open_trades: int = 2

    # Cooldown
    cooldown_after_big_pnl: int = 4 * 3

    # Entry context thresholds
    ma_distance_threshold: float = 0.00159
    candle_move_threshold: float = 0.008
    impulse_move_threshold_pct: float = 1.5
    impulse_lookback: int = 5
    late_entry_atr_mult: float = 0.8
    late_entry_body_ratio: float = 0.8
    late_entry_ema_pct: float = 0.005

    # Entry and exit controls
    entry_score_threshold: int = 9
    exit_score_threshold: int = 6
    slope_window: int = 5
    trail_activate_pct: float = 0.007
    trail_retrace_pct: float = 0.003
    loss_exit_pct_1: float = 0.05
    loss_exit_pct_2: float = 0.04
    profit_exit_pct_1: float = 0.15
    profit_exit_pct_2: float = 0.10
    loss_exit_pct: float = 0.0
    profit_exit_pct: float = 0.0
    loss_lock_step_pct: float = 0.01
    adx_exit_threshold: float = 15.0
    adx_exit_lookback: int = 1
    entry_adx_threshold: float = 20.5
    entry_atr_threshold: float = 1.2
    opposite_atr_body_mult: float = 0.6
    sharp_move_threshold_pct: float = 12.0
    sharp_move_lookback_candles: int = 600
    post_cross_penalty_candles: int = 15
    consecutive_losses_stop_until_month: int = 5

    # Indicator periods
    period_adx: int = 14
    period_atr: int = 14
    period_atr_ma: int = 21
    period_vol_avg: int = 12
    period_rsi: int = 14
    volume_spike_multiplier: float = 1.24
    ema_16_period: int = 16
    ma_50_period: int = 50
    ma_100_period: int = 102
    ma_200_period: int = 198

    # Chart settings
    plot_max_candles: int = 1200
    plot_end_offset: int = 0
    plot_step_candles: int = 300
    plot_min_zoom_candles: int = 80
    plot_max_render_candles: int = 1600
    plot_zoom_in_factor: float = 0.8
    plot_zoom_out_factor: float = 1.6
    plot_window_width_scale: float = 0.94
    plot_window_height_scale: float = 0.90
    plot_drag_preview_factor: float = 0.42
    plot_drag_update_interval_ms: int = 16
    plot_yscale_drag_sensitivity: float = 0.0030
    plot_post_cross_penalty_markers: bool = True

    # Score weights
    entry_score_cross: int = 1
    entry_score_ema_vs_ma50: int = 3
    entry_score_ma_trend: int = 1
    entry_score_ma_distance_or_candle: int = 1
    entry_score_adx: int = 1
    entry_score_volume: int = 2
    entry_late_penalty: int = 1
    exit_score_loss_guard_1: int = 3
    exit_score_loss_guard_2: int = 1
    exit_score_profit_guard_1: int = 3
    exit_score_profit_guard_2: int = 3
    exit_score_loss_guard: int = 0
    exit_score_profit_guard: int = 0
    exit_score_ema_slope: int = 1
    exit_score_ema_cross: int = 3
    exit_score_ma_trend: int = 1
    exit_score_trailing: int = 1
    exit_score_adx: int = 1
    exit_score_opposite_candle: int = 1
    post_cross_penalty_score: int = 3


@dataclass
class MAStrategyConfig(BaseStrategyConfig):
    pass


@dataclass
class RSIStrategyConfig(BaseStrategyConfig):
    leverage: float = 1
    trade_amount_percent: float = 0.10
    monthly_profit_close_filter: bool = False
    monthly_loss_close_filter: bool = False
    adx_filter: bool = False
    volume_filter: bool = False
    atr_filter: bool = False
    max_open_trades: int = 5
    safe_leverage_low: float = 1
    safe_leverage_med: float = 1
    safe_leverage_high: float = 1
    period_rsi: int = 10

    # RSI strategy controls
    symbol_change_pct: float = 0.0
    more_symbol_change_pct: float = 0.05
    rsi_symbol_change_pct: float = 0.02
    max_trade_change_pct: float = 0.0
    static_dynamic_money_pct: float = 0.90
    rsi_open_value: int = 35
    rsi_close_value: float = 90
    add_remove_maxtrades_power: bool = True


def build_ma_strategy_config(tune=None):
    return _apply_common_tune(MAStrategyConfig(), tune)


def build_rsi_strategy_config(tune=None):
    return _apply_common_tune(RSIStrategyConfig(), tune)
