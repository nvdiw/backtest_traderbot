''' NOTE : set setting with param_grid= {...}
    for example : 'x': [1, 2]
                  'y': [a, b]
 4 test
   ma_strategy(x= 1, y= a)
   ma_strategy(x= 1, y= b)
   ma_strategy(x= 2, y= a)
   ma_strategy(x= 2, y= b)
 if we have more setting we have more tests

    please command param_grid and write new param_grid= {...}
    if you don't we have restart PC :)
'''
import itertools
import csv
import time
import multiprocessing
import argparse
import os
from ma_strategy import ma_strategy
from spot_limbian_strategy import spot_limbian_strategy
from rsi_strategy import rsi_strategy
import json

# Grid to search (kept reasonable to limit runtime)
param_grid = {
    'slope_window': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    'entry_score_threshold': [i for i in range(1, 19)],
    'exit_score_threshold': [i for i in range(1, 22)],
    'ma_distance_threshold': [0.0015, 0.0020, 0.0025],
    'candle_move_threshold': [0.006, 0.008, 0.010],
    'impulse_move_threshold_pct': [1.0, 1.5, 2.0, 2.5, 3.0],
    'impulse_lookback': [3, 4, 5, 6, 7],
    'late_entry_atr_mult': [0.8, 1.0, 1.2, 1.4, 1.6],
    'late_entry_body_ratio': [0.4, 0.5, 0.6, 0.7, 0.8],
    'late_entry_ema_pct': [0.002, 0.003, 0.004, 0.005, 0.006],
    'trail_activate_pct': [0.006, 0.007, 0.008],
    'trail_retrace_pct': [0.003, 0.004, 0.005],
    'loss_exit_pct': [i/100 for i in range(1, 11)],
    'profit_exit_pct': [i/100 for i in range(1, 11)],
    'adx_exit_threshold': [14, 15, 16, 17, 18.0, 19, 20],
    'adx_exit_lookback': [1, 2, 3, 4, 5],
    'entry_adx_threshold': [i/10 for i in range(100, 306, 5)],
    'entry_atr_threshold': [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
    'period_adx': [10, 12, 14, 16, 18, 20],
    'period_atr': [10, 12, 14, 16, 18, 20],
    'period_atr_ma': [i for i in range(1, 31)],
    'period_vol_avg': [10, 12, 15, 18, 21],
    'volume_spike_multiplier': [1.0, 1.1, 1.2, 1.25, 1.3, 1.4, 1.5],
    'opposite_atr_body_mult': [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
    'entry_score_cross': [1, 2, 3],
    'entry_score_ema_vs_ma50': [1, 2, 3],
    'entry_score_ma_trend': [1, 2, 3],
    'entry_score_ma_distance_or_candle': [1, 2, 3],
    'entry_score_adx': [1, 2, 3],
    'entry_score_volume': [1, 2, 3],
    'entry_late_penalty': [0, 1, 2, 3],
    'exit_score_loss_guard': [0, 1, 2, 3],
    # Multi-level loss guard params
    'loss_exit_pct_1': [0.02, 0.025, 0.03],
    'loss_exit_pct_2': [0.04, 0.045, 0.05],
    'exit_score_loss_guard_1': [1, 2],
    'exit_score_loss_guard_2': [2, 3],
    # Multi-level profit guard params
    'profit_exit_pct_1': [0.03, 0.04],
    'profit_exit_pct_2': [0.07, 0.08],
    'exit_score_profit_guard_1': [1, 2],
    'exit_score_profit_guard_2': [2, 3],

    'exit_score_profit_guard': [0, 1, 2, 3],
    'exit_score_ema_slope': [1, 2, 3],
    'exit_score_ema_cross': [1, 2, 3],
    'exit_score_ma_trend': [1, 2, 3],
    'exit_score_trailing': [1, 2, 3],
    'exit_score_adx': [1, 2, 3],
    'exit_score_opposite_candle': [1, 2, 3],
    'sharp_move_threshold_pct': [i for i in range(10, 21)],
    'sharp_move_lookback_candles': [100, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 1000],
    'post_cross_penalty_candles': [10, 15, 20],
    'post_cross_penalty_score': [1, 2, 3, 4, 5],
    'consecutive_losses_stop_until_month': [5],
    'loss_lock_step_pct': [0.01, 0.02, 0.03, 0.04, 0.05],
    'trade_amount_percent': [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    'trade_amount_percent_neworder': [0.05, 0.1, 0.15, 0.2],
    'scale_in_trigger_move_pct': [0.005, 0.01, 0.015, 0.02],
    'scale_entry_amount_percent': [0.2],
    'scale_entry_profit_trigger_pct': [0.01, 0.015, 0.02, 0.03, 0.04, 0.05],
    'scale_entry_loss_trigger_pct': [0.01, 0.015, 0.02, 0.03, 0.04, 0.05],
    'scale_entry_on_profit_enabled': [False, True],
    'scale_entry_on_loss_enabled': [False, True],
    'profit_scale_entry_filter_enabled': [False, True],
    'profit_scale_entry_min_score': [2, 3, 4],
    'profit_scale_entry_atr_ratio_min': [0.9, 1.0, 1.1, 1.2],
    'monthly_profit_percent_stop_trade': [5, 6, 7, 8, 9, 10],
    'monthly_loss_percent_stop_trade': [i for i in range(14, 31)],
    'monthly_profit_close_filter': [True, False],
    'monthly_loss_close_filter': [True, False],
    'consecutive_losses_month_stop_filter': [True, False],
    'adx_filter': [True, False],
    'volume_filter': [True, False],
    'scale_in_enabled': [True, False],
    'leverage': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    'safe_leverage_low': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    'safe_leverage_med': [2, 3, 4, 5, 6, 7, 8, 9, 10],
    'safe_leverage_high': [3, 4, 5, 6, 7, 8, 9, 10],
    'safe_leverage_balance_pct_low': [80, 75, 70, 65],
    'safe_leverage_balance_pct_med': [85, 80, 75, 70],
    'safe_leverage_balance_pct_high': [90, 85, 80, 75],
    'save_money_recover_trigger_pct': [i for i in range(60, 76)],
    'cooldown_after_big_pnl': [i for i in range(0, 300, 4)],
    'ema_16': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    'ma_50': [45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55],
    'ma_100': [100, 110, 120, 130, 140, 150],
    'ma_200': [180, 190, 200, 210, 220, 230],
    'max_open_trades': [i for i in range(1, 21)],
    'scale_entry_long_rsi': [i for i in range(10, 51)],
    'scale_entry_short_rsi': [i for i in range(50, 91)],
    'scale_exit_long_rsi': [i for i in range(70, 91)],
    'scale_exit_short_rsi': [i for i in range(10, 31)],
    'monthly_compound': [i for i in range(0, 11)],

    # ==== rsi on ma_strategy monthly filter ====
    'rsi_long_open_monthly_profit': [i for i in range(10, 31)],
    'rsi_long_close_monthly_profit': [i for i in range(40, 91)],
    'rsi_short_open_monthly_profit': [i for i in range(70, 91)],
    'rsi_short_close_monthly_profit': [i for i in range(10, 61)],
    'rsi_long_tp_pct': [i/100 for i in range(1, 9)],
    'rsi_long_sl_pct': [i/100 for i in range(1, 6)],
    'rsi_short_tp_pct': [i/100 for i in range(1, 9)],
    'rsi_short_sl_pct': [i/100 for i in range(1, 6)],
    'rsi_max_open_trades': [1],
    'rsi_trade_amount_percent': [i/10 for i in range(1, 5)],
    'rsi_leverage': [i for i in range(1, 11)],
    'rsi_cooldown_bars': [i for i in range(0, 101)],
    'rsi_cooldown_filter': [True, False],
    'lowest_rsi_last_n_value': [i for i in range(1, 10)],
    'highest_rsi_last_n_value': [i for i in range(1, 10)],
    'rsi_entry_buffer': [1, 2, 3, 4, 5, 6, 7, 8],
    'rsi_distance_threshold': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],


    # ==== spot_limbian_strategy variables ====
    'symbol_change_pct': [i/100 for i in range(-10, 11)],
    'more_symbol_change_pct': [i/100 for i in range(1, 11)],
    'max_trade_change_pct': [i/100 for i in range(5, 21)],
    'static_dynamic_money_pct': [0.85, 0.90, 0.95],
    'period_rsi': [i for i in range(6, 30)],
    'rsi_open_value': [20, 25, 30],
    'rsi_symbol_change_pct': [i/100 for i in range(1, 11)],
    'rsi_close_value': [i for i in range(70, 96)],

}

param_grid = {     
    'ma_distance_threshold': [0.0008, 0.0010, 0.0015, 0.0020, 0.0025, 0.0030, 0.005, 0.010, 0.1],
    'candle_move_threshold': [0.001, 0.002, 0.005, 0.006, 0.008, 0.010, 0.015, 0.02, 0.05, 0.1],
}

# strategies setting only one of them should be True
ma = True
spot_limbian = False
rsi = False

keys = list(param_grid.keys())
combos = list(itertools.product(*(param_grid[k] for k in keys)))
print(f"Total combinations to test: {len(combos)}")

out_dir = os.path.join('outputs', 'optimize')
out_file = os.path.join(out_dir, 'optimization_results.csv')
os.makedirs(out_dir, exist_ok=True)
while True:
    try:
        with open(out_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(
                keys + [
                    'final_balance_static',
                    'final_balance_dynamic',
                    'total_profit',
                    'total_profit_percent',
                    'closed_trades',
                    'wins',
                    'losses',
                    'maximum_drawdown',
                    'win_rate',
                    'duration_s',
                    'profit_months',
                    'loss_months',

                    # score
                    'score',

                    # RSI
                    'rsi_total_trades',
                    'rsi_wins',
                    'rsi_losses',
                    'rsi_winrate',
                    'rsi_total_profit',

                    'rsi_long_trades',
                    'rsi_long_wins',
                    'rsi_long_losses',
                    'rsi_long_winrate',
                    'rsi_long_profit',

                    'rsi_short_trades',
                    'rsi_short_wins',
                    'rsi_short_losses',
                    'rsi_short_winrate',
                    'rsi_short_profit',

                    # SCALE
                    'scale_total_trades',
                    'scale_wins',
                    'scale_losses',
                    'scale_winrate',
                    'scale_total_profit',

                    'scale_long_trades',
                    'scale_long_wins',
                    'scale_long_losses',
                    'scale_long_winrate',
                    'scale_long_profit',

                    'scale_short_trades',
                    'scale_short_wins',
                    'scale_short_losses',
                    'scale_short_winrate',
                    'scale_short_profit',
                ]
            )
        break

    except PermissionError:
        answer = input(f"please close: {out_file} after close write ok: ")
        if answer == "ok":
            print("thanks!")


def _evaluate_pair(pair):
    """Worker: receive (idx, combo) and return a tuple parent can consume safely."""
    idx, combo = pair
    tune = dict(zip(keys, combo))
    tune.update({'optimize': True})
    t0 = time.time()

    # ----strategies
    if ma:
        try:
            res = ma_strategy(tune=tune)
            err = None
        except Exception as e:
            res = None
            err = e

    elif spot_limbian:
        try:
            res = spot_limbian_strategy(tune=tune)
            err = None
        except Exception as e:
            res = None
            err = e

    elif rsi:
        try:
            res = rsi_strategy(tune=tune)
            err = None
        except Exception as e:
            res = None
            err = e
    
    duration = time.time() - t0
    return idx, tune, res, duration, err


def _result_to_row(keys, tune, res, duration):
    return [tune[k] for k in keys] + [
        res.get('final_balance_static'),
        res.get('final_balance_dynamic'),
        res.get('total_profit'),
        res.get('total_profit_percent'),
        res.get('closed_trades'),
        res.get('wins'),
        res.get('losses'),
        res.get('maximum_drawdown'),
        res.get('win_rate'),
        round(duration, 2),
        res.get('profit_months'),
        res.get('loss_months'),

        # score
        res.get('score'),

        # RSI
        res.get('rsi_total_trades'),
        res.get('rsi_wins'),
        res.get('rsi_losses'),
        res.get('rsi_winrate'),
        res.get('rsi_total_profit'),

        res.get('rsi_long_trades'),
        res.get('rsi_long_wins'),
        res.get('rsi_long_losses'),
        res.get('rsi_long_winrate'),
        res.get('rsi_long_profit'),

        res.get('rsi_short_trades'),
        res.get('rsi_short_wins'),
        res.get('rsi_short_losses'),
        res.get('rsi_short_winrate'),
        res.get('rsi_short_profit'),

        # SCALE
        res.get('scale_total_trades'),
        res.get('scale_wins'),
        res.get('scale_losses'),
        res.get('scale_winrate'),
        res.get('scale_total_profit'),

        res.get('scale_long_trades'),
        res.get('scale_long_wins'),
        res.get('scale_long_losses'),
        res.get('scale_long_winrate'),
        res.get('scale_long_profit'),

        res.get('scale_short_trades'),
        res.get('scale_short_wins'),
        res.get('scale_short_losses'),
        res.get('scale_short_winrate'),
        res.get('scale_short_profit'),
    ]


def _append_rows(path, rows):
    if not rows:
        return
    with open(path, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def main(workers: int, chunksize: int, flush_every: int, log_every: int):
    best = None
    start_time_all = time.time()
    total = len(combos)
    rows_buffer = []
    completed = 0

    if chunksize <= 0:
        if workers and workers > 1:
            chunksize = max(1, total // (workers * 8))
        else:
            chunksize = 1

    # try parallel execution (parent does all file I/O)
    if workers and workers > 1:
        with multiprocessing.Pool(processes=workers) as pool:
            for idx, tune, res, duration, err in pool.imap_unordered(_evaluate_pair, enumerate(combos, 1), chunksize=chunksize):
                completed += 1
                if err:
                    print(f"Combo {idx}/{len(combos)} {tune} raised error: {err}")
                    continue

                rows_buffer.append(_result_to_row(keys, tune, res, duration))
                if len(rows_buffer) >= flush_every:
                    _append_rows(out_file, rows_buffer)
                    rows_buffer.clear()

                if log_every > 0 and (completed % log_every == 0 or completed == total):
                    print(f"[{completed}/{total}] last_idx={idx} duration={duration:.2f}s")

                if best is None or res.get('total_profit', -1) > best['total_profit']:
                    best = {'tune': tune, **res}
    else:
        # fallback to sequential (original behaviour)
        for idx, combo in enumerate(combos, 1):
            completed += 1
            idx, tune, res, duration, err = _evaluate_pair((idx, combo))
            if err:
                print(f"Combo {idx}/{len(combos)} {tune} raised error: {err}")
                continue

            rows_buffer.append(_result_to_row(keys, tune, res, duration))
            if len(rows_buffer) >= flush_every:
                _append_rows(out_file, rows_buffer)
                rows_buffer.clear()

            if log_every > 0 and (completed % log_every == 0 or completed == total):
                print(f"[{completed}/{total}] last_idx={idx} duration={duration:.2f}s")

            if best is None or res.get('total_profit', -1) > best['total_profit']:
                best = {'tune': tune, **res}

    _append_rows(out_file, rows_buffer)

    print('Total duration (s):', time.time() - start_time_all)
    print('Best:')
    print(json.dumps(best, indent=4, ensure_ascii=False))

    # Save best to a small file
    best_file = os.path.join(out_dir, 'best_params.txt')
    with open(best_file, 'w') as f:
        f.write(str(best) + '\n')

    print('Results saved to', out_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optimize ma_strategy (parallel).')
    parser.add_argument('-w', '--workers', type=int, default=min(8, (os.cpu_count() or 1)),
                        help='number of worker processes (default: min(8, cpu_count))')
    parser.add_argument('--chunksize', type=int, default=0,
                        help='imap_unordered chunksize (0=auto)')
    parser.add_argument('--flush-every', type=int, default=32,
                        help='flush result rows to CSV every N finished combos')
    parser.add_argument('--log-every', type=int, default=10,
                        help='print progress every N finished combos (0=silent)')
    args = parser.parse_args()
    main(args.workers, args.chunksize, args.flush_every, args.log_every)

