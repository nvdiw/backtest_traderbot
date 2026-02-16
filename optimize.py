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
from functools import partial
from ma_strategy import ma_strategy

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
    'loss_exit_pct': [0.01, 0.02, 0.03],
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
    'entry_score_close_vs_ema16': [1, 2, 3],
    'entry_score_ma_trend': [1, 2, 3],
    'entry_score_ma_distance_or_candle': [1, 2, 3],
    'entry_score_adx': [1, 2, 3],
    'entry_score_volume': [1, 2, 3],
    'entry_late_penalty': [0, 1, 2, 3],
    'exit_score_loss_guard': [1, 2, 3],
    'exit_score_ema_slope': [1, 2, 3],
    'exit_score_ema_cross': [1, 2, 3],
    'exit_score_ma_trend': [1, 2, 3],
    'exit_score_trailing': [1, 2, 3],
    'exit_score_adx': [1, 2, 3],
    'exit_score_opposite_candle': [1, 2, 3],
    'trade_amount_percent': [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    'monthly_profit_percent_stop_trade': [5, 6, 7, 8, 9, 10],
    'monthly_close_filter': [True, False],
    'adx_filter': [True, False],
    'volume_filter': [True, False],
    'leverage': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    'safe_leverage_low': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    'safe_leverage_med': [2, 3, 4, 5, 6, 7, 8, 9, 10],
    'safe_leverage_high': [3, 4, 5, 6, 7, 8, 9, 10],
    'cooldown_after_big_pnl': [i for i in range(0, 300, 4)],
    'ema_16': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    'ma_50': [45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55],
    'ma_100': [100, 110, 120, 130, 140, 150],
    'ma_200': [180, 190, 200, 210, 220, 230]
}

param_grid = {'entry_adx_threshold': [i/10 for i in range(200, 211, 1)]
}

keys = list(param_grid.keys())
combos = list(itertools.product(*(param_grid[k] for k in keys)))
print(f"Total combinations to test: {len(combos)}")

out_file = 'optimization_results.csv'
while True:
    try:
        with open(out_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(keys + ['final_balance', 'total_profit', 'total_profit_percent', 'closed_trades', 'wins', 'losses', 'maximum_drawdown', 'duration_s', 'profit_more_than_8%'])
        break

    except PermissionError:
        answer = input("please close: optimization_results.csv after close write ok: ")
        if answer == "ok":
            print("thanks!")


def _evaluate_pair(pair):
    """Worker: receive (idx, combo) and return a tuple parent can consume safely."""
    idx, combo = pair
    tune = dict(zip(keys, combo))
    tune.update({'optimize': True})
    t0 = time.time()
    try:
        res = ma_strategy(tune=tune)
        err = None
    except Exception as e:
        res = None
        err = e
    duration = time.time() - t0
    return idx, tune, res, duration, err


def _write_result_row(out_file, keys, tune, res, duration):
    row = [tune[k] for k in keys] + [res.get('final_balance'), res.get('total_profit'), res.get('total_profit_percent'), res.get('closed_trades'), res.get('wins'), res.get('losses'), res.get('maximum_drawdown'), round(duration, 2), res.get('profit_more_than_8%')]
    with open(out_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(row)


def main(workers: int):
    best = None
    start_time_all = time.time()

    pairs = list(enumerate(combos, 1))

    # try parallel execution (parent does all file I/O)
    if workers and workers > 1:
        with multiprocessing.Pool(processes=workers) as pool:
            for idx, tune, res, duration, err in pool.imap_unordered(_evaluate_pair, pairs, chunksize=1):
                if err:
                    print(f"Combo {idx}/{len(combos)} {tune} raised error: {err}")
                    continue

                _write_result_row(out_file, keys, tune, res, duration)
                print(f"[{idx}/{len(combos)}] tune={tune} profit={res.get('final_balance')}")

                if best is None or res.get('total_profit', -1) > best['total_profit']:
                    best = {'tune': tune, **res}
    else:
        # fallback to sequential (original behaviour)
        for idx, combo in pairs:
            idx, tune, res, duration, err = _evaluate_pair((idx, combo))
            if err:
                print(f"Combo {idx}/{len(combos)} {tune} raised error: {err}")
                continue

            _write_result_row(out_file, keys, tune, res, duration)
            print(f"[{idx}/{len(combos)}] tune={tune} profit={res.get('final_balance')}")

            if best is None or res.get('total_profit', -1) > best['total_profit']:
                best = {'tune': tune, **res}

    print('Total duration (s):', time.time() - start_time_all)
    print('Best:', best)

    # Save best to a small file
    with open('best_params.txt', 'w') as f:
        f.write(str(best) + '\n')

    print('Results saved to', out_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Optimize ma_strategy (parallel).')
    parser.add_argument('-w', '--workers', type=int, default=min(8, (os.cpu_count() or 1)),
                        help='number of worker processes (default: min(8, cpu_count))')
    args = parser.parse_args()
    main(args.workers)

