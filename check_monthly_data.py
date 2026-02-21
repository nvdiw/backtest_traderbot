"""
check_monthly_data.py

Reads trade orders CSV, aggregates trade statistics by the month of the CLOSE time,
and writes monthly summary CSV with summary metrics.

Usage:
    python check_monthly_data.py

Output columns:
- month (YYYY-MM)
- total_trades
- total_wins
- total_losses
- total_longs
- total_shorts
- monthly_profit (sum of `profit`)
- monthly_fee_paid (sum of `fee_paid`)
- total_duration_minutes (sum of `duration_minutes_total`)
- win_rate
- avg_profit_per_trade
- first_balance (balance_before of first trade in the month)
- last_balance (balance_after of last trade in the month)
- net_percent ((last_balance/first_balance - 1) * 100) when available

Default paths:
- input:  `outputs/trades/data_orders.csv`
- output: `outputs/monthly/monthly_data_orders.csv`
"""

import os
import pandas as pd

IN_FILE = os.path.join('outputs', 'trades', 'data_orders.csv')
OUT_FILE = os.path.join('outputs', 'monthly', 'monthly_data_orders.csv')


def summarize_monthly(df: pd.DataFrame) -> pd.DataFrame:
    # remove summary rows and ensure datetime parsing
    df = df[df['type'].astype(str).str.upper() != 'SUMMARY'].copy()

    # parse close_time
    df['close_time'] = pd.to_datetime(df['close_time'], errors='coerce')
    df['open_time'] = pd.to_datetime(df['open_time'], errors='coerce')

    # assign month based on CLOSE time (trades that close in a month count to that month)
    df['month'] = df['close_time'].dt.to_period('M').astype(str)

    # coerce numeric columns
    for col in ['profit', 'fee_paid', 'duration_minutes_total', 'balance_before', 'balance_after', 'profit_percent']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    groups = []
    for month, g in df.groupby('month'):
        total_trades = len(g)
        total_wins = (g['profit'] > 0).sum()
        total_losses = (g['profit'] <= 0).sum()
        total_longs = (g['type'].astype(str).str.upper() == 'LONG').sum()
        total_shorts = (g['type'].astype(str).str.upper() == 'SHORT').sum()
        monthly_profit = g['profit'].sum(min_count=1)
        monthly_fee_paid = g['fee_paid'].sum(min_count=1) if 'fee_paid' in g.columns else None
        total_duration_minutes = g['duration_minutes_total'].sum(min_count=1) if 'duration_minutes_total' in g.columns else None
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        avg_profit_per_trade = (monthly_profit / total_trades) if total_trades > 0 else 0

        first_balance = g.sort_values('close_time').iloc[0]['balance_before'] if 'balance_before' in g.columns and not g.empty else None
        last_balance = g.sort_values('close_time').iloc[-1]['balance_after'] if 'balance_after' in g.columns and not g.empty else None
        if pd.notna(first_balance) and pd.notna(last_balance) and first_balance != 0:
            net_percent = (last_balance / first_balance - 1) * 100
        else:
            net_percent = None

        groups.append({
            'month': month,
            'total_trades': int(total_trades),
            'total_wins': int(total_wins),
            'total_losses': int(total_losses),
            'total_longs': int(total_longs),
            'total_shorts': int(total_shorts),
            'monthly_profit': float(monthly_profit) if pd.notna(monthly_profit) else 0.0,
            'monthly_fee_paid': float(monthly_fee_paid) if pd.notna(monthly_fee_paid) else 0.0,
            'total_duration_minutes': float(total_duration_minutes) if pd.notna(total_duration_minutes) else 0.0,
            'win_rate': float(win_rate),
            'avg_profit_per_trade': float(avg_profit_per_trade),
            'first_balance': float(first_balance) if pd.notna(first_balance) else None,
            'last_balance': float(last_balance) if pd.notna(last_balance) else None,
            'net_percent': float(net_percent) if net_percent is not None else None,
        })

    out_df = pd.DataFrame(groups).sort_values('month')
    return out_df


def main():
    # preserve previous behavior when run as script (prints)
    write_monthly_summary(IN_FILE, OUT_FILE, quiet=False)


def write_monthly_summary(in_file=IN_FILE, out_file=OUT_FILE, quiet=True):
    """Read `in_file`, summarize by close-month, and write `out_file`.
    If `quiet` is True, do not print to terminal (suitable for calling from main.py).
    """
    if not os.path.isfile(in_file):
        if not quiet:
            print(f"{in_file} not found.")
        return False

    df = pd.read_csv(in_file)
    if df.empty:
        if not quiet:
            print('No data found in', in_file)
        return False

    out_df = summarize_monthly(df)
    out_dir = os.path.dirname(out_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out_df.to_csv(out_file, index=False)
    if not quiet:
        print(f"Wrote monthly summary to: {out_file}")
        print(out_df.to_string(index=False))
    return True


if __name__ == '__main__':
    main()
