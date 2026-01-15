# NOTE : set setting with param_grid= {...}
# for example : 'x': [1, 2]
#               'y': [a, b]
# 4 test
#   ma_strategy(x= 1, y= a)
#   ma_strategy(x= 1, y= b)
#   ma_strategy(x= 2, y= a)
#   ma_strategy(x= 2, y= b)
# if we have more setting we have more tests

import itertools
import csv
import time
from main import ma_strategy

# Grid to search (kept reasonable to limit runtime)
param_grid = {
    'slope_window': [2, 3, 4],
    'exit_score_threshold': [2, 3, 4],
    'atr_drawdown_mult': [1.0, 1.5],
    'atr_time_multiplier': [2, 4],
    'atr_time_min': [1, 3],
    'baseline_time_pct': [0.01, 0.02],
    'trade_amount_percent': [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    'monthly_profit_percent_stop_trade': [5, 6, 7, 8, 9, 10],
    'monthly_close_filter': [True, False],
    'adx_filter': [True, False],
    'volume_filter': [True, False],
    'leverage': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    'safe_leverage': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    'cooldown_after_big_pnl': [i for i in range(4, 300, 4)]
}

keys = list(param_grid.keys())
combos = list(itertools.product(*(param_grid[k] for k in keys)))
print(f"Total combinations to test: {len(combos)}")

out_file = 'optimization_results.csv'
while True:
    try:
        with open(out_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(keys + ['final_balance', 'total_profit', 'total_profit_percent', 'closed_trades', 'wins', 'losses', 'duration_s', 'profit_more_than_8%'])
        break

    except PermissionError:
        answer = input("please close: optimization_results.csv after close write ok: ")
        if answer == "ok":
            print("thanks!")

best = None
start_time_all = time.time()
for idx, combo in enumerate(combos, 1):
    tune = dict(zip(keys, combo))
    t0 = time.time()
    try:
        res = ma_strategy(tune=tune)
    except Exception as e:
        print(f"Combo {idx}/{len(combos)} {tune} raised error: {e}")
        continue
    duration = time.time() - t0

    row = [tune[k] for k in keys] + [res.get('final_balance'), res.get('total_profit'), res.get('total_profit_percent'), res.get('closed_trades'), res.get('wins'), res.get('losses'), round(duration, 2), res.get('profit_more_than_8%')]
    with open(out_file, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(row)

    print(f"[{idx}/{len(combos)}] tune={tune} profit={row[keys.__len__()]}")

    if best is None or res.get('total_profit', -1) > best['total_profit']:
        best = {'tune': tune, **res}

print('Total duration (s):', time.time() - start_time_all)
print('Best:', best)

# Save best to a small file
with open('best_params.txt', 'w') as f:
    f.write(str(best) + '\n')

print('Results saved to', out_file)

