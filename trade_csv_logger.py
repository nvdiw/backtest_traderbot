import pandas as pd


class TradeCSVLogger:
    """Lightweight CSV logger.
    - In normal mode it collects rows and writes a CSV on save_csv().
    - In optimize mode (optimize=True) it becomes a no-op to avoid disk I/O
      and reduce per-trade overhead (much faster for grid search).
    """
    def __init__(self, optimize: bool = False):
        self.optimize = bool(optimize)
        if self.optimize:
            # keep only a tiny counter to preserve minimal bookkeeping
            self._count = 0
        else:
            self.rows = []

    def log_trade(
        self,
        trade_type,
        open_time,
        close_time,
        entry_price,
        close_price,
        balance_before,
        balance_after,
        margin,
        leverage,
        trade_amount_percent,
        profit,
        profit_percent,
        pnl_percent,
        fee,
        days,
        hours,
        minutes,
        save_money,
        profit_percent_per_month
    ):
        if self.optimize:
            # no per-trade allocations during optimization
            self._count += 1
            return

        self.rows.append({
            "type": trade_type,
            "open_time": open_time,
            "close_time": close_time,
            "entry_price": entry_price,
            "close_price": close_price,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "amount": margin,
            "leverage": leverage,
            "trade_amount_percent": trade_amount_percent,
            "profit": profit,
            "profit_percent": profit_percent,
            "pnl_percent": pnl_percent,
            "fee_paid": fee,
            "duration_minutes_total": days * 24 * 60 + hours * 60 + minutes,
            "duration_days": days,
            "duration_hours": hours,
            "duration_minutes": minutes,
            "save_money": save_money,
            "profit_percent_per_month": profit_percent_per_month
        })

    def save_csv(
        self,
        first_balance,
        final_balance,
        total_profit,
        total_profit_percent,
        total_fee,
        start_time,
        end_time,
        days,
        hours,
        minutes,
        file_name: str = "data_orders.csv"
    ):
        if self.optimize:
            # do not write any files during optimization
            return {"rows_logged": getattr(self, "_count", 0)}

        columns = [
            "type",
            "open_time",
            "close_time",
            "entry_price",
            "close_price",
            "balance_before",
            "balance_after",
            "amount",
            "leverage",
            "trade_amount_percent",
            "profit",
            "profit_percent",
            "pnl_percent",
            "fee_paid",
            "duration_minutes_total",
            "duration_days",
            "duration_hours",
            "duration_minutes",
            "save_money",
            "profit_percent_per_month",
        ]
        df = pd.DataFrame(self.rows, columns=columns)

        summary_row = {
            "type": "SUMMARY",
            "open_time": start_time,
            "close_time": end_time,
            "entry_price": None,
            "close_price": None,
            "balance_before": first_balance,
            "balance_after": final_balance,
            "profit": total_profit,
            "profit_percent": total_profit_percent,
            "fee_paid": total_fee,
            "duration_days": days,
            "duration_hours": hours,
            "duration_minutes": minutes
        }
        summary_row_full = {col: summary_row.get(col, None) for col in columns}

        if df.empty:
            df = pd.DataFrame([summary_row_full], columns=columns)
        else:
            df.loc[len(df), columns] = [summary_row_full[col] for col in columns]
        while True:
            try:
                df.to_csv(file_name, index=False, encoding="utf-8")
                break
            except PermissionError:
                answer = input("please close: data_orders.csv after close write ok: ")
                if answer == "ok":
                    print("thanks!")
