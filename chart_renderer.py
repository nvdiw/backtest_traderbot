import time
import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import transforms as mtransforms
from matplotlib.backend_bases import MouseButton


def render_backtest_chart(
    chart_data,
    close_prices,
    close_times,
    open_prices,
    high_prices,
    low_prices,
    ema_16,
    ma_50,
    ma_100,
    ma_200,
    rsi_values,
    long_open_points,
    long_close_points,
    short_open_points,
    short_close_points,
    penalty_long_points,
    penalty_short_points,
    long_open_reasons,
    long_close_reasons,
    short_open_reasons,
    short_close_reasons,
    penalty_long_reasons,
    penalty_short_reasons,
    plot_end_offset,
    plot_max_candles,
    plot_step_candles,
    plot_min_zoom_candles,
    plot_max_render_candles,
    plot_zoom_in_factor,
    plot_zoom_out_factor,
    plot_window_width_scale,
    plot_window_height_scale,
    plot_drag_preview_factor,
    plot_drag_update_interval_ms,
    plot_yscale_drag_sensitivity,
    balance,
    profits_lst,
    t_profit_percent,
    count_closed_orders,
    total_wins,
    total_losses,
    max_drawdown,
    lst_profit_percent_per_month,
):
    ypoints_total_balance = [row[1] for row in chart_data]
    zpoints_total_balance = [row[2] for row in chart_data]
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
        "rsi": "#E84393",
        "rsi_oversold": "#4CD47A",
        "rsi_overbought": "#FF6B7A",
        "rsi_mid": "#A7B4C8",
        "mark": "#5FA2D9",
        "long_open": "#7FE0B0",
        "long_close": "#2FCF82",
        "short_open": "#FF98A8",
        "short_close": "#E96A7E",
        "penalty": "#FFD84D",
        "equity": "#5CC8F2",
        "equity_d": "#F2B15C",
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
    
    fig = plt.figure(figsize=(14.5, 10.2), facecolor=chart_palette["bg"])
    grid = fig.add_gridspec(3, 1, height_ratios=[3, 1, 0.8], hspace=0.04)
    ax_price = fig.add_subplot(grid[0])
    ax_equity = fig.add_subplot(grid[1], sharex=ax_price)
    ax_rsi = fig.add_subplot(grid[2], sharex=ax_price)

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
        "hline_rsi": None,
        "price_label": None,
        "balance_label": None,
        "rsi_label": None,
        "time_label": None,
        "marker_hover_points": [],
        "visible_times": None,
        "marker_tooltip_artist": None,
        "debug_overlay_artist": None,
        "rendering": False,
        "last_click_time": 0.0,
        "last_click_axis": None,
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
    
    def downsample_last_valid_with_index(arr, step):
        if step <= 1:
            n = len(arr)
            idx_map = np.arange(n, dtype=int)
            nan_mask = ~np.isfinite(np.asarray(arr, dtype=float))
            idx_map[nan_mask] = -1
            return np.asarray(arr, dtype=float), idx_map
        n = len(arr)
        out_vals = []
        out_idx = []
        for s in range(0, n, step):
            e = min(s + step, n)
            seg = np.asarray(arr[s:e], dtype=float)
            valid_idx = np.where(np.isfinite(seg))[0]
            if valid_idx.size > 0:
                last_local = int(valid_idx[-1])
                out_vals.append(float(seg[last_local]))
                out_idx.append(int(s + last_local))
            else:
                out_vals.append(np.nan)
                out_idx.append(-1)
        return np.asarray(out_vals, dtype=float), np.asarray(out_idx, dtype=int)
    
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
            full_equity_static = np.asarray(ypoints_total_balance[plot_start:plot_end], dtype=float)
            full_equity_dynamic = np.asarray(zpoints_total_balance[plot_start:plot_end], dtype=float)
            full_rsi = np.asarray(rsi_values[plot_start:plot_end], dtype=float)
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
            penalty_long_arr = np.full(n_full, np.nan, dtype=float)
            penalty_short_arr = np.full(n_full, np.nan, dtype=float)
    
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
            place_trade_markers(penalty_long_points, penalty_long_arr)
            place_trade_markers(penalty_short_points, penalty_short_arr)
    
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
    
            # For RSI, use a smaller step to keep the line smooth
            if nav_state.get("preview_mode"):
                # During drag, still keep RSI smooth (use half the normal step)
                rsi_step = max(1, render_step // 2)
            else:
                # Normal mode: RSI can use same step as candles
                rsi_step = render_step

            ds_open, ds_high, ds_low, ds_close, ds_times = downsample_ohlc(
                full_open, full_high, full_low, full_close, full_close_times, render_step
            )
            ds_ema16 = downsample_last(full_ema16, render_step)
            ds_ma50 = downsample_last(full_ma50, render_step)
            ds_ma100 = downsample_last(full_ma100, render_step)
            ds_ma200 = downsample_last(full_ma200, render_step)
            ds_equity = downsample_last(full_equity_static, render_step)
            dd_equity = downsample_last(full_equity_dynamic, render_step)
            ds_mark = downsample_last_valid(mark_arr, render_step)
            ds_rsi = downsample_last_valid(full_rsi, render_step)
            ds_long_open, ds_long_open_marker_idx = downsample_last_valid_with_index(long_open_arr, render_step)
            ds_long_close, ds_long_close_marker_idx = downsample_last_valid_with_index(long_close_arr, render_step)
            ds_short_open, ds_short_open_marker_idx = downsample_last_valid_with_index(short_open_arr, render_step)
            ds_short_close, ds_short_close_marker_idx = downsample_last_valid_with_index(short_close_arr, render_step)
            ds_penalty_long, ds_penalty_long_marker_idx = downsample_last_valid_with_index(penalty_long_arr, render_step)
            ds_penalty_short, ds_penalty_short_marker_idx = downsample_last_valid_with_index(penalty_short_arr, render_step)
    
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
            equity_series_static = pd.Series(ds_equity, index=time_index)
            equity_series_dynamic = pd.Series(dd_equity, index=time_index)
            rsi_series = pd.Series(ds_rsi, index=time_index)
            mark_series = pd.Series(ds_mark, index=time_index)
            long_open_series = pd.Series(ds_long_open, index=time_index)
            long_close_series = pd.Series(ds_long_close, index=time_index)
            short_open_series = pd.Series(ds_short_open, index=time_index)
            short_close_series = pd.Series(ds_short_close, index=time_index)
            penalty_long_series = pd.Series(ds_penalty_long, index=time_index)
            penalty_short_series = pd.Series(ds_penalty_short, index=time_index)
    
            ax_price.cla()
            ax_equity.cla()
            ax_rsi.cla()
            nav_state["marker_hover_points"] = []
    
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
            if (not preview_mode) and has_finite(penalty_long_series):
                add_plots.append(
                    mpf.make_addplot(
                        penalty_long_series,
                        ax=ax_price,
                        type="scatter",
                        marker="X",
                        markersize=54,
                        color=chart_palette["penalty"],
                        alpha=0.95,
                    )
                )
            if (not preview_mode) and has_finite(penalty_short_series):
                add_plots.append(
                    mpf.make_addplot(
                        penalty_short_series,
                        ax=ax_price,
                        type="scatter",
                        marker="X",
                        markersize=54,
                        color=chart_palette["penalty"],
                        alpha=0.95,
                    )
                )
            if has_finite(equity_series_static):
                add_plots.append(
                    mpf.make_addplot(equity_series_static, ax=ax_equity, color=chart_palette["equity"], width=1.2)
                )

            if has_finite(equity_series_dynamic):
                add_plots.append(
                    mpf.make_addplot(equity_series_dynamic, ax=ax_equity, color=chart_palette["equity_d"], width=1.2)
                )

            if has_finite(rsi_series):
                add_plots.append(
                    mpf.make_addplot(rsi_series, ax=ax_rsi, color=chart_palette["rsi"], width=1.2)
                )
                
                # line 30 (oversold)
                oversold_line = pd.Series([30] * len(time_index), index=time_index)
                add_plots.append(
                    mpf.make_addplot(oversold_line, ax=ax_rsi, color=chart_palette["rsi_oversold"], 
                                    width=0.8, linestyle="--", alpha=0.7)
                )
                
                # line 70 (overbought)
                overbought_line = pd.Series([70] * len(time_index), index=time_index)
                add_plots.append(
                    mpf.make_addplot(overbought_line, ax=ax_rsi, color=chart_palette["rsi_overbought"], 
                                    width=0.8, linestyle="--", alpha=0.7)
                )
                
                # line 50 (mid)
                mid_line = pd.Series([50] * len(time_index), index=time_index)
                add_plots.append(
                    mpf.make_addplot(mid_line, ax=ax_rsi, color=chart_palette["rsi_mid"], 
                                    width=0.5, linestyle=":", alpha=0.5)
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
                        
            ax_rsi.set_facecolor(chart_palette["panel_bg"])
            ax_rsi.yaxis.label.set_color(chart_palette["text"])
            ax_rsi.tick_params(axis="x", colors=chart_palette["muted"])
            ax_rsi.tick_params(axis="y", colors=chart_palette["muted"])
            ax_rsi.set_axisbelow(True)
            ax_rsi.grid(
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
                f"BTC - OHLC + MAs | Last: ${last_close_price:,.2f} | Candles: {len(price_df)} (x{render_step}) | Offset: {offset_clamped} | Drag/Wheel/\u2190/\u2192 | \u2191 oldest | \u2193 latest | Left-click near trade marker for reasons",
                color=chart_palette["text"],
            )
            ax_price.set_ylabel("BTC Price")
            ax_equity.set_ylabel("Balance ($)")
            ax_price.tick_params(labelbottom=False)

            ax_rsi.set_ylabel("RSI", color=chart_palette["text"], fontsize=10)
            ax_rsi.set_ylim(0, 100)

            ax_rsi.axhspan(0, 30, alpha=0.08, color=chart_palette["rsi_oversold"], zorder=0)
            ax_rsi.axhspan(70, 100, alpha=0.08, color=chart_palette["rsi_overbought"], zorder=0)

            ax_rsi.tick_params(labelbottom=False)

            # visual separator between price panel and equity panel
            ax_price.spines["bottom"].set_visible(True)
            ax_price.spines["bottom"].set_color(chart_palette["divider"])
            ax_price.spines["bottom"].set_linewidth(1.4)
            ax_equity.spines["top"].set_visible(True)
            ax_equity.spines["top"].set_color(chart_palette["divider"])
            ax_equity.spines["top"].set_linewidth(1.4)
            ax_rsi.spines["top"].set_visible(True)
            ax_rsi.spines["top"].set_color(chart_palette["divider"])
            ax_rsi.spines["top"].set_linewidth(1.2)
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
            nav_state["vline_rsi"] = ax_rsi.axvline(
                x_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.75, visible=False, zorder=30
            )
            nav_state["hline_price"] = ax_price.axhline(
                y_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.9, visible=False, zorder=30
            )
            nav_state["hline_equity"] = ax_equity.axhline(
                y_eq_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.85, visible=False, zorder=30
            )

            # Create RSI horizontal line and label
            y_rsi_bottom, y_rsi_top = ax_rsi.get_ylim()
            y_rsi_mid = (y_rsi_bottom + y_rsi_top) / 2.0

            nav_state["hline_rsi"] = ax_rsi.axhline(
                y_rsi_mid, color=cross_color, linewidth=0.8, linestyle="--", alpha=0.85, visible=False, zorder=30
            )

            # Create label for RSI values
            rsi_label_transform = mtransforms.blended_transform_factory(ax_rsi.transAxes, ax_rsi.transData)
            nav_state["rsi_label"] = ax_rsi.text(
                0.002, y_rsi_mid, "",
                transform=rsi_label_transform,
                ha="left", va="center",
                fontsize=8, color=chart_palette["label_fg"],
                bbox=dict(
                    boxstyle="round,pad=0.18",
                    facecolor=chart_palette["label_bg"],
                    edgecolor=chart_palette["label_edge"],
                    linewidth=0.8,
                ),
                visible=False, zorder=31
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
            time_transform = mtransforms.blended_transform_factory(ax_equity.transData, ax_equity.transAxes)
            nav_state["time_label"] = ax_equity.text(
                x_mid,
                0.02,
                "",
                transform=time_transform,
                ha="center",
                va="bottom",
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
            # Prevent stacking fig-level text artists across re-renders.
            old_marker_tooltip = nav_state.get("marker_tooltip_artist")
            if old_marker_tooltip is not None:
                try:
                    old_marker_tooltip.remove()
                except Exception:
                    pass
            old_debug_overlay = nav_state.get("debug_overlay_artist")
            if old_debug_overlay is not None:
                try:
                    old_debug_overlay.remove()
                except Exception:
                    pass
            nav_state["marker_tooltip_artist"] = fig.text(
                0.992,
                0.968,
                "",
                transform=fig.transFigure,
                ha="right",
                va="top",
                fontsize=8,
                color=chart_palette["label_fg"],
                bbox=dict(
                    boxstyle="round,pad=0.34",
                    facecolor=chart_palette["label_bg"],
                    edgecolor=chart_palette["label_edge"],
                    linewidth=0.9,
                ),
                visible=False,
                zorder=120,
            )
            nav_state["debug_overlay_artist"] = fig.text(
                0.992,
                0.998,
                "DEBUG overlay ON",
                transform=fig.transFigure,
                ha="right",
                va="top",
                fontsize=8,
                color="#EAF2FF",
                bbox=dict(
                    boxstyle="round,pad=0.26",
                    facecolor="#1E2A39",
                    edgecolor="#6C7F97",
                    linewidth=0.9,
                    alpha=0.92,
                ),
                visible=True,
                zorder=140,
            )
    
            def register_hover_points(values_arr, marker_local_idx, reasons_map):
                if reasons_map is None:
                    return
                finite_mask = np.isfinite(values_arr)
                if not finite_mask.any():
                    return
                for j in np.where(finite_mask)[0]:
                    src_local_idx = int(marker_local_idx[j]) if j < len(marker_local_idx) else -1
                    if src_local_idx < 0:
                        continue
                    src_idx = int(plot_start + src_local_idx)
                    reason_text = reasons_map.get(src_idx)
                    if not reason_text:
                        reason_text = f"Trade marker at index {src_idx}\nReason data not found in current run."
                    ts = time_index[j]
                    if isinstance(ts, pd.Timestamp):
                        ts_dt = ts.to_pydatetime()
                    else:
                        ts_dt = pd.Timestamp(ts, tz="UTC").to_pydatetime()
                    nav_state["marker_hover_points"].append(
                        {
                            "x": float(mdates.date2num(ts_dt)),
                            "y": float(values_arr[j]),
                            "text": reason_text,
                        }
                    )
    
            register_hover_points(ds_long_open, ds_long_open_marker_idx, long_open_reasons)
            register_hover_points(ds_long_close, ds_long_close_marker_idx, long_close_reasons)
            register_hover_points(ds_short_open, ds_short_open_marker_idx, short_open_reasons)
            register_hover_points(ds_short_close, ds_short_close_marker_idx, short_close_reasons)
            register_hover_points(ds_penalty_long, ds_penalty_long_marker_idx, penalty_long_reasons)
            register_hover_points(ds_penalty_short, ds_penalty_short_marker_idx, penalty_short_reasons)
            debug_overlay_artist = nav_state.get("debug_overlay_artist")
            if debug_overlay_artist is not None:
                debug_overlay_artist.set_text(
                    f"DEBUG overlay ON | markers: {len(nav_state.get('marker_hover_points', []))}"
                )
                debug_overlay_artist.set_visible(True)
            nav_state["visible_times"] = list(time_index)
    
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
        for key in (
            "vline_price",
            "vline_equity",
            "vline_rsi",
            "hline_price",
            "hline_equity",
            "hline_rsi",
            "price_label",
            "balance_label",
            "time_label",
            "rsi_label",
            "marker_tooltip_artist",
        ):
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
    
    def find_nearest_marker_point(event):
        if event is None or event.x is None or event.y is None:
            return None
        if event.inaxes is None or id(event.inaxes) != id(ax_price):
            return None
        if not ax_price.bbox.contains(event.x, event.y):
            return None
        hover_points = nav_state.get("marker_hover_points", [])
        if not hover_points:
            return None
        nearest_point = None
        nearest_dist2 = None
        for pt in hover_points:
            px, py = ax_price.transData.transform((pt["x"], pt["y"]))
            dx = float(event.x) - float(px)
            dy = float(event.y) - float(py)
            d2 = (dx * dx) + (dy * dy)
            if nearest_dist2 is None or d2 < nearest_dist2:
                nearest_dist2 = d2
                nearest_point = pt
        return nearest_point
    
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
    
    def calculate_auto_range_for_visible_data():
        """
        Calculate y-range based on min/max of visible price and equity data
        Considers both static AND dynamic balance curves
        """
        
        # Get visible candle indices
        old_size = int(nav_state["window_size"])
        old_size = max(1, min(total_candles, old_size))
        old_offset = min(max(int(nav_state["offset"]), 0), max(0, total_candles - old_size))
        start_idx = total_candles - old_offset - old_size
        end_idx = total_candles - old_offset
        
        if start_idx < 0 or end_idx <= start_idx:
            return None, None
        
        # ============ Calculate price range ============
        visible_high = np.nanmax(high_prices[start_idx:end_idx]) if np.isfinite(high_prices[start_idx:end_idx]).any() else None
        visible_low = np.nanmin(low_prices[start_idx:end_idx]) if np.isfinite(low_prices[start_idx:end_idx]).any() else None
        
        if visible_high is not None and visible_low is not None and np.isfinite([visible_high, visible_low]).all():
            # Add 1% padding on each side
            price_range = visible_high - visible_low
            padding = price_range * 0.01 if price_range > 0 else visible_low * 0.01
            price_ylim = (visible_low - padding, visible_high + padding)
        else:
            price_ylim = None
        
        # ============ Calculate equity range (BOTH static AND dynamic) ============
        all_balance_values = []
        
        # Add static balance values (closed positions only)
        if ypoints_total_balance and len(ypoints_total_balance) >= end_idx:
            for val in ypoints_total_balance[start_idx:end_idx]:
                if val is not None and np.isfinite(val):
                    all_balance_values.append(val)
        
        # Add dynamic balance values (includes open positions)
        if zpoints_total_balance and len(zpoints_total_balance) >= end_idx:
            for val in zpoints_total_balance[start_idx:end_idx]:
                if val is not None and np.isfinite(val):
                    all_balance_values.append(val)
        
        if all_balance_values:
            max_balance = max(all_balance_values)
            min_balance = min(all_balance_values)
            balance_range = max_balance - min_balance
            # Use 2% padding for better visualization (dynamic curve has more volatility)
            padding = balance_range * 0.02 if balance_range > 0 else min_balance * 0.01
            equity_ylim = (min_balance - padding, max_balance + padding)
        else:
            equity_ylim = None
        
        return price_ylim, equity_ylim
    
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
        time_label = nav_state.get("time_label")
        marker_tooltip_artist = nav_state.get("marker_tooltip_artist")
        if None in (vline_price, vline_equity, hline_price, hline_equity, price_label, balance_label, time_label):
            return
    
        cursor_x = ax_price.transData.inverted().transform((event.x, event.y))[0]
        cursor_y_on_price = ax_price.transData.inverted().transform((event.x, event.y))[1]
        cursor_y_on_equity = ax_equity.transData.inverted().transform((event.x, event.y))[1]

        # ============ RSI Panel Hover ============
        # Get cursor position on RSI panel
        cursor_y_on_rsi = None
        if ax_rsi.bbox.contains(event.x, event.y):
            cursor_y_on_rsi = ax_rsi.transData.inverted().transform((event.x, event.y))[1]
        
        # Show/hide RSI crosshair
        hline_rsi = nav_state.get("hline_rsi")
        rsi_label = nav_state.get("rsi_label")
        vline_rsi = nav_state.get("vline_rsi")
        
        # Update vertical line for RSI
        if vline_rsi is not None:
            vline_rsi.set_xdata([cursor_x, cursor_x])
            vline_rsi.set_visible(True)
        
        if ax_rsi.bbox.contains(event.x, event.y) and cursor_y_on_rsi is not None:
            # Check if within valid RSI range (0-100)
            if 0 <= cursor_y_on_rsi <= 100:
                if hline_rsi is not None:
                    hline_rsi.set_ydata([cursor_y_on_rsi, cursor_y_on_rsi])
                    hline_rsi.set_visible(True)
                
                if rsi_label is not None:
                    rsi_label.set_y(cursor_y_on_rsi)
                    rsi_label.set_text(f"RSI: {cursor_y_on_rsi:.1f}")
                    rsi_label.set_visible(True)
            else:
                # Outside RSI range (0-100), hide crosshair
                if hline_rsi is not None:
                    hline_rsi.set_visible(False)
                if rsi_label is not None:
                    rsi_label.set_visible(False)
        else:
            # Not hovering over RSI panel
            if hline_rsi is not None:
                hline_rsi.set_visible(False)
            if rsi_label is not None:
                rsi_label.set_visible(False)

        vline_price.set_xdata([cursor_x, cursor_x])
        vline_equity.set_xdata([cursor_x, cursor_x])
        vline_price.set_visible(True)
        vline_equity.set_visible(True)
        time_label.set_x(cursor_x)
        visible_times = nav_state.get("visible_times") or []
        if len(visible_times) > 0:
            x_left, x_right = ax_price.get_xlim()
            span = float(x_right - x_left)
            if np.isfinite(span) and abs(span) > 1e-12:
                frac = float(np.clip((cursor_x - x_left) / span, 0.0, 1.0))
                idx = int(round(frac * (len(visible_times) - 1)))
                idx = int(np.clip(idx, 0, len(visible_times) - 1))
                ts = visible_times[idx]
                if not isinstance(ts, pd.Timestamp):
                    ts = pd.Timestamp(ts, tz="UTC")
                elif ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                time_label.set_text(ts.strftime("%Y-%m-%d %H:%M"))
                time_label.set_visible(True)
            else:
                time_label.set_visible(False)
        else:
            time_label.set_visible(False)
    
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
    
        # Hover tooltip for trade markers (fallback mode requested by user).
        if marker_tooltip_artist is not None:
            hit_point = find_nearest_marker_point(event)
            if hit_point is not None:
                marker_tooltip_artist.set_text(hit_point["text"])
                marker_tooltip_artist.set_visible(True)
            else:
                marker_tooltip_artist.set_visible(False)
        debug_overlay_artist = nav_state.get("debug_overlay_artist")
        if debug_overlay_artist is not None:
            in_price = ax_price.bbox.contains(event.x, event.y)
            tip = "ON" if (marker_tooltip_artist is not None and marker_tooltip_artist.get_visible()) else "OFF"
            debug_overlay_artist.set_text(
                f"DEBUG overlay ON | markers: {len(nav_state.get('marker_hover_points', []))} | in_price: {in_price} | tip: {tip}"
            )
            debug_overlay_artist.set_visible(True)
    
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
        is_right_click = (button == MouseButton.RIGHT) or (button == 3) or ("right" in button_text)
    
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
    
    def on_double_click(event):
        """Handle double click on price or equity panels to auto-fit y-axis"""
        if event.inaxes not in (ax_price, ax_equity):
            return
        
        price_ylim, equity_ylim = calculate_auto_range_for_visible_data()
        
        if event.inaxes == ax_price and price_ylim is not None:
            nav_state["fixed_ylim_price"] = price_ylim
            ax_price.set_ylim(price_ylim)
            fig.canvas.draw_idle()
            
        elif event.inaxes == ax_equity and equity_ylim is not None:
            nav_state["fixed_ylim_equity"] = equity_ylim
            ax_equity.set_ylim(equity_ylim)
            fig.canvas.draw_idle()

        elif event.inaxes == ax_rsi:
            # Reset RSI to 0-100 range on double click
            ax_rsi.set_ylim(0, 100)
            fig.canvas.draw_idle()

    def on_click(event):
        # Detect double-click (within 0.35s and same axis)
        now = time.perf_counter()
        last_time = nav_state.get("last_click_time", 0.0)
        last_axis = nav_state.get("last_click_axis", None)
        is_double = (now - last_time < 0.35) and (last_axis == event.inaxes)
        nav_state["last_click_time"] = now
        nav_state["last_click_axis"] = event.inaxes
        if is_double:
            on_double_click(event)

    cid_click = fig.canvas.mpl_connect("button_press_event", on_click)
    
    def on_release(event):
        if nav_state["rendering"]:
            return
    
        active_ax = event.inaxes if (event.inaxes in fig.axes) else get_axis_by_id(nav_state.get("press_axis_id"))
        if active_ax is None:
            active_ax = ax_price
        toolbar_mode = get_toolbar_mode()
        drag_mode = nav_state.get("drag_mode")
    
        if drag_mode == "yscale":
            # If toolbar pan/zoom is active, sync x-range immediately on right-drag release
            # so newly visible candles render without requiring an extra click.
            if ("pan" in toolbar_mode) or ("zoom" in toolbar_mode):
                set_fixed_ylim_for_axis(ax_price, ax_price.get_ylim())
                set_fixed_ylim_for_axis(ax_equity, ax_equity.get_ylim())
                nav_state["press_px"] = None
                nav_state["preview_mode"] = False
                nav_state["did_live_drag"] = False
                sync_from_axis_xlim(active_ax)
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
