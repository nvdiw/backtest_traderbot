# Calculate Trade Duration
def trade_duration(open_time: str, close_time: str):
    # format: YYYY-MM-DD HH:MM:SS.microseconds

    def parse(t):
        t = t.strip()
        date, time = t.split(" ")
        y, m, d = map(int, date.split("-"))
        h, mi, s = time.split(":")
        s = int(float(s))  # drop microseconds
        return y, m, d, int(h), int(mi), s

    def to_seconds(y, m, d, h, mi, s):
        # days per month (no leap year handling for simplicity)
        mdays = [31,28,31,30,31,30,31,31,30,31,30,31]

        days = y * 365 + sum(mdays[:m-1]) + (d - 1)
        return days * 86400 + h * 3600 + mi * 60 + s

    o = to_seconds(*parse(open_time))
    c = to_seconds(*parse(close_time))

    diff = c - o

    days = diff // 86400
    diff %= 86400
    hours = diff // 3600
    diff %= 3600
    minutes = diff // 60

    return days, hours, minutes


# Trade manager class to encapsulate open/close logic without changing behavior
class TradeManager:
    def __init__(self, csv_logger, first_balance, monthly_profit_percent_stop_trade, monthly_loss_percent_stop_trade,
                 tactical_balance, monthly_profit_close_filter, monthly_loss_close_filter, monthly_compound, leverage, safe_leverage_low, safe_leverage_med,
                 safe_leverage_high, safe_leverage_balance_pct_low, safe_leverage_balance_pct_med,
                 safe_leverage_balance_pct_high, save_money_recover_trigger_pct, verbose=True) :
        self.csv_logger = csv_logger
        self.first_balance = first_balance
        self.monthly_profit_percent_stop_trade = monthly_profit_percent_stop_trade
        self.monthly_loss_percent_stop_trade = monthly_loss_percent_stop_trade
        self.tactical_balance = tactical_balance
        self.monthly_profit_close_filter = monthly_profit_close_filter
        self.monthly_loss_close_filter = monthly_loss_close_filter
        self.monthly_compound = monthly_compound
        self.leverage = leverage
        self.safe_leverage_low = safe_leverage_low
        self.safe_leverage_med = safe_leverage_med
        self.safe_leverage_high = safe_leverage_high
        self.safe_leverage_balance_pct_low = safe_leverage_balance_pct_low
        self.safe_leverage_balance_pct_med = safe_leverage_balance_pct_med
        self.safe_leverage_balance_pct_high = safe_leverage_balance_pct_high
        self.save_money_recover_trigger_pct = save_money_recover_trigger_pct
        self.verbose = bool(verbose)
        self.equity_peak = None
        # self.just_one_time = True

    @staticmethod
    def _safe_percent(value, base):
        return (value * 100 / base) if base != 0 else 0

    @staticmethod
    def _resolve_csv_balances(
        balance_before_free,
        margin,
        profit,
        balance_before_override=None,
        remaining_open_margin=0,
    ):
        # CSV balance_before/after are portfolio-level values for readability:
        # before = free capital + current margin + other locked margins, excluding save_money.
        balance_before = balance_before_free + margin + remaining_open_margin
        if balance_before_override is not None:
            balance_before = balance_before_override
        balance_after = balance_before + profit
        return balance_before, balance_after

    @staticmethod
    def _resolve_total_assets(balance, save_money, remaining_open_margin, remaining_open_equity=None):
        open_position_value = remaining_open_margin if remaining_open_equity is None else remaining_open_equity
        return balance + open_position_value + save_money

    def _update_drawdown(self, equity_curve, max_drawdown, total_assets):
        equity_curve.append(total_assets)
        if self.equity_peak is None:
            self.equity_peak = max(equity_curve) if equity_curve else total_assets
        elif total_assets > self.equity_peak:
            self.equity_peak = total_assets

        peak = self.equity_peak
        if peak <= 0:
            return equity_curve, max_drawdown
        drawdown = (total_assets - peak) / peak * 100
        return equity_curve, min(max_drawdown, drawdown)


    # open long processes
    def open_long(self, i, open_prices, open_times,
                    balance, balance_without_fee,
                    trade_amount_percent, margin_balance, margin_balance_no_fee, tactical_balance, leverage = None):

        entry_price = open_prices[i]

        portfolio_balance_before_open = margin_balance if margin_balance is not None else balance
        portfolio_balance_before_open_no_fee = margin_balance_no_fee if margin_balance_no_fee is not None else balance_without_fee

        # ---------- Margin ----------
        if balance >= trade_amount_percent * tactical_balance:
            margin = trade_amount_percent * tactical_balance
        else:
            margin = balance
        margin = max(0.0, min(margin, balance))
        if margin <= 0:
            return None

        # ---------- Margin No Fee ----------
        if balance_without_fee >= trade_amount_percent * tactical_balance:
            margin_no_fee = trade_amount_percent * tactical_balance
        else:
            margin_no_fee = balance_without_fee
        margin_no_fee = max(0.0, min(margin_no_fee, balance_without_fee))
        
        # ---------- Leverage ----------
        # In multi-position mode, free balance drops after each open.
        # Use total active capital (free + locked margin) for leverage safety tiers.
        leverage_ref_balance = margin_balance if margin_balance is not None else balance
        leverage_ref_balance = max(0.0, leverage_ref_balance)
        if leverage == None:
            if leverage_ref_balance <= tactical_balance * self.safe_leverage_balance_pct_low / 100:
                leverage = self.safe_leverage_low
            elif leverage_ref_balance <= tactical_balance * self.safe_leverage_balance_pct_med / 100:
                leverage = self.safe_leverage_med
            elif leverage_ref_balance <= tactical_balance * self.safe_leverage_balance_pct_high / 100:
                leverage =  self.safe_leverage_high
            else:
                leverage = self.leverage    # = 10
        else:
            leverage = leverage

        position_value = margin * leverage
        position_size = position_value / entry_price

        position_value_no_fee = margin_no_fee * leverage
        position_size_no_fee = position_value_no_fee / entry_price

        # update balance after allocating margin
        balance -= margin
        balance_without_fee -= margin_no_fee

        # update open time and current position
        open_time_value = open_times[i]
        current_position = "long"

        if self.verbose:
            print("Open LONG at price:", entry_price, "$", "| Open Time:", open_time_value, "| leverage:", leverage)

        return {
            'entry_price': entry_price,
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'balance_before_trade': portfolio_balance_before_open,
            'balance_before_trade_no_fee': portfolio_balance_before_open_no_fee,
            'margin': margin,
            'trade_amount_percent': trade_amount_percent,
            'leverage': leverage,
            'position_value': position_value,
            'position_size': position_size,
            'margin_no_fee': margin_no_fee,
            'position_value_no_fee': position_value_no_fee,
            'position_size_no_fee': position_size_no_fee,
            'open_time_value': open_time_value,
            'current_position': current_position
        }


    # close long processes
    def close_long(self, i, open_prices, open_times,
                entry_price, position_size, position_size_no_fee,
                fee_rate, margin, margin_no_fee,
                balance, balance_without_fee,
                deducting_fee_total, profits_lst, total_profit_percent,
                count_closed_orders, equity_curve,
                max_drawdown, total_wins, total_wins_long, total_losses,
                total_long, cooldown_after_big_pnl, leverage,
                cooldown_until_index, open_time_value, csv_logger, trade_amount_percent, 
                profit_percent_per_month, save_money, trade_power, trade_id, remaining_open_margin,
                remaining_open_margin_no_fee, tactical_balance, reason_to_close,
                balance_before_close_snapshot=None, balance_before_close_no_fee_snapshot=None,
                balance_before_log_override=None, balance_before_log_override_no_fee=None, remaining_open_equity=None):

        close_price = open_prices[i]
        if balance_before_close_snapshot is None:
            free_balance_before_close = balance
        else:
            free_balance_before_close = balance_before_close_snapshot
        if balance_before_close_no_fee_snapshot is None:
            free_balance_before_close_no_fee = balance_without_fee
        else:
            free_balance_before_close_no_fee = balance_before_close_no_fee_snapshot

        # PnL
        pnl = position_size * (close_price - entry_price)
        pnl_no_fee = position_size_no_fee * (close_price - entry_price)

        # Fee like Toobit
        entry_fee = entry_price * position_size * fee_rate
        exit_fee = close_price * position_size * fee_rate
        total_fee = entry_fee + exit_fee

        # Update balance
        balance += margin + pnl - total_fee
        balance_without_fee += margin_no_fee + pnl_no_fee

        # per-position net result (stable under multi-position mode)
        profit = pnl - total_fee

        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_override=balance_before_log_override,
            remaining_open_margin=remaining_open_margin
        )

        logged_balance_before_no_fee, logged_balance_after_no_fee = self._resolve_csv_balances(
            free_balance_before_close_no_fee,
            margin_no_fee,
            pnl_no_fee,
            balance_before_override=balance_before_log_override_no_fee,
            remaining_open_margin=remaining_open_margin_no_fee
        )

        profit_percent = self._safe_percent(profit, logged_balance_before)
        total_assets = self._resolve_total_assets(balance, save_money, remaining_open_margin, remaining_open_equity)
        profit_percent_per_month = (((total_assets - save_money) * 100) / tactical_balance) - 100
        pnl_percent = self._safe_percent(pnl, margin)

        deducting_fee_total += total_fee
        profits_lst.append(profit)
        total_profit_percent += profit_percent
        count_closed_orders += 1

        # ---- calculate max drawdown ----
        equity_curve, max_drawdown = self._update_drawdown(equity_curve, max_drawdown, total_assets)

        # ---- count wins and losses ----
        if profit_percent > 0:
            total_wins += 1
            total_wins_long += 1
        else:
            total_losses += 1

        # ---- count LONG trades ----
        total_long += 1

        # ---- COOLDOWN AFTER BIG PROFIT ----
        pnl_percent_without_leverage = (((pnl / margin) * 100 ) / leverage) if (margin != 0 and leverage != 0) else 0
        if pnl_percent_without_leverage >= 4:
            cooldown_until_index = i + cooldown_after_big_pnl
            if self.verbose:
                print(f"🟡 Cooldown Activated (LONG) until candle index {cooldown_until_index}")

        close_time_value = open_times[i]
        days, hours, minutes = trade_duration(open_time_value, close_time_value)


        if self.verbose:
            print("Close LONG at price:", close_price, "$", "| Close Time:", close_time_value, "| leverage:", leverage)
            print("Balance:", round(logged_balance_before, 2), "$", "→", round(logged_balance_after, 2), "$", "| Save Money:", round(save_money, 2), "$")
            print("Balance (no fee):",
                round(logged_balance_before_no_fee, 2), "$", "→", round(logged_balance_after_no_fee, 2), "$")
            print("pnl:", round(pnl, 2), "$ |", round(pnl_percent, 2), "% |" , "Amount:", round(margin), "$")
            print("fee:", round(total_fee, 2), "$")
            print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
            print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
            print("-" * 90)


        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_override=balance_before_log_override,
            remaining_open_margin=remaining_open_margin
        )
        has_other_open_positions_at_close = remaining_open_margin > 0
        log_total_assets = total_assets
        log_profit_percent_per_month = (((log_total_assets - save_money) * 100) / tactical_balance) - 100
        if reason_to_close == "rsi_ma_strategy" and log_profit_percent_per_month > 0:
            log_profit_percent_per_month = 0
        csv_logger.log_trade(
            trade_id,
            "LONG",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(tactical_balance, 2),
            round(log_total_assets, 2),
            round(logged_balance_before, 2),
            round(logged_balance_after, 2),
            round(margin , 2),
            leverage,
            trade_amount_percent,
            round(profit, 2),
            round(profit_percent, 2),
            round(pnl_percent, 2),
            round(total_fee, 4),
            days,
            hours,
            minutes,
            round(save_money, 6),
            log_profit_percent_per_month,
            has_other_open_positions_at_close,
            reason_to_close
        )
        profit_percent_per_month = log_profit_percent_per_month

        current_position = None

        return {
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'deducting_fee_total': deducting_fee_total,
            'close_price': close_price,
            'close_time_value': close_time_value,
            'leverage': leverage,
            'margin': margin,
            'total_fee': total_fee,
            'profit': profit,
            'profit_percent': profit_percent,
            'profits_lst': profits_lst,
            'total_profit_percent': total_profit_percent,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'count_closed_orders': count_closed_orders,
            'equity_curve': equity_curve,
            'max_drawdown': max_drawdown,
            'total_wins': total_wins,
            'total_wins_long': total_wins_long,
            'total_losses': total_losses,
            'total_long': total_long,
            'cooldown_until_index': cooldown_until_index,
            'current_position': current_position,
            'trade_power': trade_power,
            'profit_percent_per_month': profit_percent_per_month,
            'save_money' : save_money,
            'logged_balance_before': logged_balance_before,
            'logged_balance_after': logged_balance_after,
            'days': days,
            'hours': hours,
            'minutes': minutes,
        }
    

    # open short processes
    def open_short(self, i, open_prices, open_times,
                    balance, balance_without_fee,
                    trade_amount_percent, margin_balance, margin_balance_no_fee, tactical_balance, leverage = None):

        entry_price = open_prices[i]

        portfolio_balance_before_open = margin_balance if margin_balance is not None else balance
        portfolio_balance_before_open_no_fee = margin_balance_no_fee if margin_balance_no_fee is not None else balance_without_fee

        # ---------- Margin ----------
        if balance >= trade_amount_percent * tactical_balance:
            margin = trade_amount_percent * tactical_balance
        else:
            margin = balance
        margin = max(0.0, min(margin, balance))
        if margin <= 0:
            return None

        # ---------- Margin No Fee ----------
        if balance_without_fee >= trade_amount_percent * tactical_balance:
            margin_no_fee = trade_amount_percent * tactical_balance
        else:
            margin_no_fee = balance_without_fee
        margin_no_fee = max(0.0, min(margin_no_fee, balance_without_fee))

        # ---------- Leverage ----------
        # In multi-position mode, free balance drops after each open.
        # Use total active capital (free + locked margin) for leverage safety tiers.
        leverage_ref_balance = margin_balance if margin_balance is not None else balance
        leverage_ref_balance = max(0.0, leverage_ref_balance)
        if leverage == None:
            if leverage_ref_balance <= tactical_balance * self.safe_leverage_balance_pct_low / 100:
                leverage = self.safe_leverage_low  # 2 low
            elif leverage_ref_balance <= tactical_balance * self.safe_leverage_balance_pct_med / 100:
                leverage = self.safe_leverage_med  # 3 med
            elif leverage_ref_balance <= tactical_balance * self.safe_leverage_balance_pct_high / 100:
                leverage = self.safe_leverage_high # 4 high
            else:
                leverage = self.leverage    # = 10
        else:
            leverage = leverage

        position_value = margin * leverage
        position_size = position_value / entry_price

        position_value_no_fee = margin_no_fee * leverage
        position_size_no_fee = position_value_no_fee / entry_price

        # update balance after allocating margin
        balance -= margin
        balance_without_fee -= margin_no_fee

        # update open time and current position
        open_time_value = open_times[i]
        current_position = "short"

        if self.verbose:
            print("Open SHORT at price:", entry_price, "$", "| Open Time:", open_time_value, "| leverage:", leverage)

        return {
            'entry_price': entry_price,
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'balance_before_trade': portfolio_balance_before_open,
            'balance_before_trade_no_fee': portfolio_balance_before_open_no_fee,
            'margin': margin,
            'trade_amount_percent': trade_amount_percent,
            'leverage': leverage,
            'position_value': position_value,
            'position_size': position_size,
            'margin_no_fee': margin_no_fee,
            'position_value_no_fee': position_value_no_fee,
            'position_size_no_fee': position_size_no_fee,
            'open_time_value': open_time_value,
            'current_position': current_position
        }


    # close short processes
    def close_short(self, i, open_prices, open_times,
            entry_price, position_size, position_size_no_fee,
            fee_rate, margin, margin_no_fee,
            balance, balance_without_fee,
            deducting_fee_total, profits_lst, total_profit_percent,
            count_closed_orders, equity_curve,
            max_drawdown, total_wins, total_wins_short, total_losses,
            total_short, cooldown_after_big_pnl, leverage,
            cooldown_until_index, open_time_value, csv_logger, trade_amount_percent, 
            profit_percent_per_month, save_money, trade_power, trade_id, remaining_open_margin,
            remaining_open_margin_no_fee, tactical_balance, reason_to_close,
            balance_before_close_snapshot=None, balance_before_close_no_fee_snapshot=None,
            balance_before_log_override=None, balance_before_log_override_no_fee=None, remaining_open_equity=None):

        close_price = open_prices[i]
        if balance_before_close_snapshot is None:
            free_balance_before_close = balance
        else:
            free_balance_before_close = balance_before_close_snapshot
        if balance_before_close_no_fee_snapshot is None:
            free_balance_before_close_no_fee = balance_without_fee
        else:
            free_balance_before_close_no_fee = balance_before_close_no_fee_snapshot

        # PnL
        pnl = position_size * (entry_price - close_price)
        pnl_no_fee = position_size_no_fee * (entry_price - close_price)

        # Fee like Toobit
        entry_fee = entry_price * position_size * fee_rate
        exit_fee = close_price * position_size * fee_rate
        total_fee = entry_fee + exit_fee

        # Update balance
        balance += margin + pnl - total_fee
        balance_without_fee += margin_no_fee + pnl_no_fee

        # per-position net result (stable under multi-position mode)
        profit = pnl - total_fee

        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_override=balance_before_log_override,
            remaining_open_margin=remaining_open_margin
        )

        logged_balance_before_no_fee, logged_balance_after_no_fee = self._resolve_csv_balances(
            free_balance_before_close_no_fee,
            margin_no_fee,
            pnl_no_fee,
            balance_before_override=balance_before_log_override_no_fee,
            remaining_open_margin=remaining_open_margin_no_fee
        )

        profit_percent = self._safe_percent(profit, logged_balance_before)
        total_assets = self._resolve_total_assets(balance, save_money, remaining_open_margin, remaining_open_equity)
        profit_percent_per_month = (((total_assets - save_money) * 100) / tactical_balance) - 100
        pnl_percent = self._safe_percent(pnl, margin)

        deducting_fee_total += total_fee
        profits_lst.append(profit)
        total_profit_percent += profit_percent
        count_closed_orders += 1

        # ---- calculate max drawdown ----
        equity_curve, max_drawdown = self._update_drawdown(equity_curve, max_drawdown, total_assets)

        # ---- count wins and losses ----
        if profit_percent > 0:
            total_wins += 1
            total_wins_short += 1
        else:
            total_losses += 1

        # ---- count shorts ----
        total_short += 1

        # ---- COOLDOWN AFTER BIG PROFIT ----
        pnl_percent_without_leverage = (((pnl / margin) * 100) / leverage) if (margin != 0 and leverage != 0) else 0
        if pnl_percent_without_leverage >= 4:
            cooldown_until_index = i + cooldown_after_big_pnl
            if self.verbose:
                print(f"🟡 Cooldown Activated (SHORT) until candle index {cooldown_until_index}")

        close_time_value = open_times[i]
        days, hours, minutes = trade_duration(open_time_value, close_time_value)


        if self.verbose:
            print("Close SHORT at price:", close_price, "$", "| Close Time:", close_time_value, "| leverage:", leverage)
            print("Balance:", round(logged_balance_before, 2), "$", "→", round(logged_balance_after, 2), "$", "| Save Money:", round(save_money, 2), "$")
            print("Balance (no fee):",
                round(logged_balance_before_no_fee, 2), "$", "→", round(logged_balance_after_no_fee, 2), "$")
            print("pnl:", round(pnl, 2), "$ |", round(pnl_percent, 2), "% |", "Amount:", round(margin), "$")
            print("fee:", round(total_fee, 2), "$")
            print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
            print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
            print("-" * 90)


        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_override=balance_before_log_override,
            remaining_open_margin=remaining_open_margin
        )
        has_other_open_positions_at_close = remaining_open_margin > 0
        log_total_assets = total_assets
        log_profit_percent_per_month = (((log_total_assets - save_money) * 100) / tactical_balance) - 100
        if reason_to_close == "rsi_ma_strategy" and log_profit_percent_per_month > 0:
            log_profit_percent_per_month = 0
        csv_logger.log_trade(
            trade_id,
            "SHORT",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(tactical_balance, 2),
            round(log_total_assets, 2),
            round(logged_balance_before, 2),
            round(logged_balance_after, 2),
            round(margin , 2),
            leverage,
            trade_amount_percent,
            round(profit, 2),
            round(profit_percent, 2),
            round(pnl_percent, 2),
            round(total_fee, 4),
            days,
            hours,
            minutes,
            round(save_money, 6),
            log_profit_percent_per_month,
            has_other_open_positions_at_close,
            reason_to_close
        )
        profit_percent_per_month = log_profit_percent_per_month

        current_position = None

        return {
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'deducting_fee_total': deducting_fee_total,
            'close_price': close_price,
            'close_time_value': close_time_value,
            'leverage': leverage,
            'margin': margin,
            'total_fee': total_fee,
            'profit': profit,
            'profit_percent': profit_percent,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'profits_lst': profits_lst,
            'total_profit_percent': total_profit_percent,
            'pnl_percent': pnl_percent,
            'count_closed_orders': count_closed_orders,
            'equity_curve': equity_curve,
            'max_drawdown': max_drawdown,
            'total_wins': total_wins,
            'total_wins_short': total_wins_short,
            'total_losses': total_losses,
            'total_short': total_short,
            'cooldown_until_index': cooldown_until_index,
            'current_position': current_position,
            'trade_power': trade_power,
            'profit_percent_per_month': profit_percent_per_month,
            'save_money' : save_money,
            'logged_balance_before': logged_balance_before,
            'logged_balance_after': logged_balance_after,
            'days': days,
            'hours': hours,
            'minutes': minutes,
        }


    # check liquidation long
    def check_liquidation_long(
        self, i, low_prices, close_times,
        entry_price, leverage, margin,
        balance, balance_without_fee,
        deducting_fee_total, count_closed_orders,
        total_losses, total_long, equity_curve,
        save_money, max_drawdown, open_time_value,
        csv_logger, trade_amount_percent,
        total_liquids, trade_id, remaining_open_margin,
        remaining_open_margin_no_fee, tactical_balance, reason_to_close,
        balance_before_close_snapshot=None,
        balance_before_close_no_fee_snapshot=None,
        balance_before_log_override=None,
        balance_before_log_override_no_fee=None,
        remaining_open_equity=None
    ):

        liquid_price_long = entry_price * (1 - 1 / leverage)

        # --------------------------
        # NOT LIQUIDATED
        # --------------------------
        if low_prices[i] > liquid_price_long:
            return {
                'liquidated': False,
                'balance': balance,
                'balance_without_fee': balance_without_fee,
                'deducting_fee_total': deducting_fee_total,
                'count_closed_orders': count_closed_orders,
                'total_losses': total_losses,
                'total_long': total_long,
                'equity_curve': equity_curve,
                'max_drawdown': max_drawdown,
                'close_price': None,
                'close_time_value': None
            }

        # --------------------------
        # LIQUIDATION HAPPENS
        # --------------------------
        close_price = liquid_price_long
        close_time_value = close_times[i]

        if balance_before_close_snapshot is None:
            free_balance_before_close = balance
        else:
            free_balance_before_close = balance_before_close_snapshot

        if balance_before_close_no_fee_snapshot is None:
            free_balance_before_close_no_fee = balance_without_fee
        else:
            free_balance_before_close_no_fee = balance_before_close_no_fee_snapshot

        # --------------------------
        # PnL (FULL LOSS)
        # --------------------------
        pnl = -margin
        pnl_no_fee = -margin

        entry_fee = 0
        exit_fee = 0
        total_fee = 0

        # --------------------------
        # BALANCE UPDATE (same logic style as close_long)
        # --------------------------
        balance += margin + pnl - total_fee
        balance_without_fee += margin + pnl_no_fee

        profit = pnl - total_fee

        # --------------------------
        # CSV BALANCE (same as close_long)
        # --------------------------
        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_override=balance_before_log_override,
            remaining_open_margin=remaining_open_margin
        )

        logged_balance_before_no_fee, logged_balance_after_no_fee = self._resolve_csv_balances(
            free_balance_before_close_no_fee,
            margin,
            pnl_no_fee,
            balance_before_override=balance_before_log_override_no_fee,
            remaining_open_margin=remaining_open_margin_no_fee
        )

        # --------------------------
        # METRICS (aligned with close_long)
        # --------------------------
        profit_percent = self._safe_percent(profit, logged_balance_before)
        pnl_percent = self._safe_percent(pnl, margin)

        deducting_fee_total += total_fee
        count_closed_orders += 1
        total_losses += 1
        total_long += 1
        total_liquids += 1

        total_assets = self._resolve_total_assets(
            balance,
            save_money,
            remaining_open_margin,
            remaining_open_equity
        )

        equity_curve, max_drawdown = self._update_drawdown(
            equity_curve,
            max_drawdown,
            total_assets
        )

        profit_percent_per_month = (
            ((total_assets - save_money) * 100) / tactical_balance
        ) - 100

        # --------------------------
        # LOG TIME
        # --------------------------
        days, hours, minutes = trade_duration(open_time_value, close_time_value)

        if self.verbose:
            print("🔴 LONG LIQUIDATED at price:", round(close_price, 2),
                "| Time:", close_time_value)

        # --------------------------
        # CSV LOG (same structure as close_long)
        # --------------------------
        has_other_open_positions_at_close = remaining_open_margin > 0

        csv_logger.log_trade(
            trade_id,
            "LONG_LIQUIDATED",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(tactical_balance, 2),
            round(total_assets, 2),
            round(logged_balance_before, 2),
            round(logged_balance_after, 2),
            round(margin, 2),
            leverage,
            trade_amount_percent,
            round(profit, 2),
            round(profit_percent, 2),
            round(pnl_percent, 2),
            round(total_fee, 4),
            days,
            hours,
            minutes,
            round(save_money, 6),
            profit_percent_per_month,
            has_other_open_positions_at_close,
            reason_to_close
        )

        # --------------------------
        # RETURN
        # --------------------------
        return {
            'liquidated': True,
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'deducting_fee_total': deducting_fee_total,
            'count_closed_orders': count_closed_orders,
            'total_losses': total_losses,
            'total_long': total_long,
            'equity_curve': equity_curve,
            'max_drawdown': max_drawdown,
            'close_price': close_price,
            'close_time_value': close_time_value,
            'total_liquids': total_liquids
        }


    # check liquidation short
    def check_liquidation_short(
        self, i, high_prices, close_times,
        entry_price, leverage, margin,
        balance, balance_without_fee,
        deducting_fee_total, count_closed_orders,
        total_losses, total_short, equity_curve,
        save_money, max_drawdown, open_time_value,
        csv_logger, trade_amount_percent,
        total_liquids, trade_id, remaining_open_margin,
        remaining_open_margin_no_fee, tactical_balance, reason_to_close,
        balance_before_close_snapshot=None,
        balance_before_close_no_fee_snapshot=None,
        balance_before_log_override=None,
        balance_before_log_override_no_fee=None,
        remaining_open_equity=None
    ):

        liquid_price_short = entry_price * (1 + 1 / leverage)

        # --------------------------
        # NOT LIQUIDATED
        # --------------------------
        if high_prices[i] < liquid_price_short:
            return {
                'liquidated': False,
                'balance': balance,
                'balance_without_fee': balance_without_fee,
                'deducting_fee_total': deducting_fee_total,
                'count_closed_orders': count_closed_orders,
                'total_losses': total_losses,
                'total_short': total_short,
                'equity_curve': equity_curve,
                'max_drawdown': max_drawdown,
                'close_price': None,
                'close_time_value': None
            }

        # --------------------------
        # LIQUIDATION HAPPENS
        # --------------------------
        close_price = liquid_price_short
        close_time_value = close_times[i]

        if balance_before_close_snapshot is None:
            free_balance_before_close = balance
        else:
            free_balance_before_close = balance_before_close_snapshot

        if balance_before_close_no_fee_snapshot is None:
            free_balance_before_close_no_fee = balance_without_fee
        else:
            free_balance_before_close_no_fee = balance_before_close_no_fee_snapshot

        # --------------------------
        # PnL (FULL LOSS)
        # --------------------------
        pnl = -margin
        pnl_no_fee = -margin

        total_fee = 0

        # --------------------------
        # BALANCE UPDATE (same logic as close_long style)
        # --------------------------
        balance += margin + pnl - total_fee
        balance_without_fee += margin + pnl_no_fee

        profit = pnl - total_fee

        # --------------------------
        # CSV BALANCE (aligned with close_long)
        # --------------------------
        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_override=balance_before_log_override,
            remaining_open_margin=remaining_open_margin
        )

        logged_balance_before_no_fee, logged_balance_after_no_fee = self._resolve_csv_balances(
            free_balance_before_close_no_fee,
            margin,
            pnl_no_fee,
            balance_before_override=balance_before_log_override_no_fee,
            remaining_open_margin=remaining_open_margin_no_fee
        )

        # --------------------------
        # METRICS (aligned with close_long)
        # --------------------------
        profit_percent = self._safe_percent(profit, logged_balance_before)
        pnl_percent = self._safe_percent(pnl, margin)

        deducting_fee_total += total_fee
        count_closed_orders += 1
        total_losses += 1
        total_short += 1
        total_liquids += 1

        total_assets = self._resolve_total_assets(
            balance,
            save_money,
            remaining_open_margin,
            remaining_open_equity
        )

        equity_curve, max_drawdown = self._update_drawdown(
            equity_curve,
            max_drawdown,
            total_assets
        )

        profit_percent_per_month = (
            ((total_assets - save_money) * 100) / tactical_balance
        ) - 100

        # --------------------------
        # TIME
        # --------------------------
        days, hours, minutes = trade_duration(open_time_value, close_time_value)

        if self.verbose:
            print("🔴 SHORT LIQUIDATED at price:", round(close_price, 2),
                "| Time:", close_time_value)

        # --------------------------
        # CSV LOG
        # --------------------------
        has_other_open_positions_at_close = remaining_open_margin > 0

        csv_logger.log_trade(
            trade_id,
            "SHORT_LIQUIDATED",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(tactical_balance, 2),
            round(total_assets, 2),
            round(logged_balance_before, 2),
            round(logged_balance_after, 2),
            round(margin, 2),
            leverage,
            trade_amount_percent,
            round(profit, 2),
            round(profit_percent, 2),
            round(pnl_percent, 2),
            round(total_fee, 4),
            days,
            hours,
            minutes,
            round(save_money, 6),
            profit_percent_per_month,
            has_other_open_positions_at_close,
            reason_to_close
        )

        # --------------------------
        # RETURN
        # --------------------------
        return {
            'liquidated': True,
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'deducting_fee_total': deducting_fee_total,
            'count_closed_orders': count_closed_orders,
            'total_losses': total_losses,
            'total_short': total_short,
            'equity_curve': equity_curve,
            'max_drawdown': max_drawdown,
            'close_price': close_price,
            'close_time_value': close_time_value,
            'total_liquids': total_liquids
        }

