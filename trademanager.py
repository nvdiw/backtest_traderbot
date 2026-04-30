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
        # self.just_one_time = True

    @staticmethod
    def _safe_percent(value, base):
        return (value * 100 / base) if base != 0 else 0

    @staticmethod
    def _resolve_csv_balances(balance_before_free, margin, profit, balance_before_override=None):
        # CSV balance_before/after are portfolio-level values for readability:
        # before = total capital before close event, after = before + net profit.
        balance_before = balance_before_free + margin
        if balance_before_override is not None:
            balance_before = balance_before_override
        balance_after = balance_before + profit
        return balance_before, balance_after


    # open long processes
    def open_long(self, i, open_prices, open_times,
                    balance, balance_without_fee,
                    trade_amount_percent, margin_balance):

        entry_price = open_prices[i]

        free_balance_before_open = balance
        free_balance_before_open_no_fee = balance_without_fee

        # ---------- Margin ----------
        if balance >= trade_amount_percent * self.tactical_balance:
            margin = trade_amount_percent * self.tactical_balance
        else:
            margin = balance
        margin = max(0.0, min(margin, balance))
        if margin <= 0:
            return None

        # ---------- Margin No Fee ----------
        if balance_without_fee >= trade_amount_percent * self.tactical_balance:
            margin_no_fee = trade_amount_percent * self.tactical_balance
        else:
            margin_no_fee = balance_without_fee
        margin_no_fee = max(0.0, min(margin_no_fee, balance_without_fee))
        
        # ---------- Leverage ----------
        # In multi-position mode, free balance drops after each open.
        # Use total active capital (free + locked margin) for leverage safety tiers.
        leverage_ref_balance = margin_balance if margin_balance is not None else balance
        leverage_ref_balance = max(0.0, leverage_ref_balance)
        if leverage_ref_balance <= self.tactical_balance * self.safe_leverage_balance_pct_low / 100:
            leverage = self.safe_leverage_low
        elif leverage_ref_balance <= self.tactical_balance * self.safe_leverage_balance_pct_med / 100:
            leverage = self.safe_leverage_med
        elif leverage_ref_balance <= self.tactical_balance * self.safe_leverage_balance_pct_high / 100:
            leverage =  self.safe_leverage_high
        else:
            leverage = self.leverage    # = 10

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
            'balance_before_trade': free_balance_before_open,
            'balance_before_trade_no_fee': free_balance_before_open_no_fee,
            'margin': margin,
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
                balance_before_close_snapshot=None, balance_before_close_no_fee_snapshot=None,
                balance_before_log_override=None):

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
        capital_before_trade = free_balance_before_close + margin
        profit_percent = self._safe_percent(profit, capital_before_trade)
        total_assets = balance + remaining_open_margin + save_money
        profit_percent_per_month = (((total_assets - save_money) * 100) / self.tactical_balance) - 100
        pnl_percent = self._safe_percent(pnl, margin)

        deducting_fee_total += total_fee
        profits_lst.append(profit)
        total_profit_percent += profit_percent
        count_closed_orders += 1

        equity_curve.append(total_assets)
        # ---- calculate max drawdown ----
        peak = max(equity_curve)
        drawdown = (balance + save_money + remaining_open_margin - peak) / peak * 100
        max_drawdown = min(max_drawdown, drawdown)

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
            logged_balance_before, logged_balance_after = self._resolve_csv_balances(
                free_balance_before_close,
                margin,
                profit
            )
            logged_balance_before_no_fee = free_balance_before_close_no_fee + margin_no_fee
            logged_balance_after_no_fee = free_balance_before_close_no_fee + margin_no_fee + pnl_no_fee
            print("Close LONG at price:", close_price, "$", "| Close Time:", close_time_value, "| leverage:", leverage)
            print("Balance:", round(logged_balance_before, 2), "$", "→", round(logged_balance_after, 2), "$", "| Save Money:", round(save_money, 2), "$")
            print("Balance (no fee):",
                round(logged_balance_before_no_fee, 2), "$", "→", round(logged_balance_after_no_fee, 2), "$")
            print("pnl:", round(pnl, 2), "$ |", round(pnl_percent, 2), "% |" , "Amount:", round(margin), "$")
            print("fee:", round(total_fee, 2), "$")
            print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
            print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
            print("-" * 90)

        used_save_money_for_monthly_loss = False
        monthly_stop_reason = None
        monthly_stop_value = None
        log_tactical_balance = self.tactical_balance

        # stop trade if we got monthly target profit
        # Apply monthly actions only after the last close in a batch.
        if trade_power and remaining_open_margin <= 0 and self.monthly_profit_close_filter == True :
            if profit_percent_per_month >= self.monthly_profit_percent_stop_trade:
                monthly_stop_reason = "profit"
                monthly_stop_value = profit_percent_per_month
                self.tactical_balance = self.tactical_balance + (self.tactical_balance * self.monthly_compound / 100)
                monthly_surplus = balance - self.tactical_balance
                if monthly_surplus > 0:
                    save_money += monthly_surplus
                balance = self.tactical_balance
                cooldown_until_index = i
                trade_power = False    # off

        # stop trade if we got monthly max loss
        if trade_power and remaining_open_margin <= 0 and self.monthly_loss_close_filter == True:
            if profit_percent_per_month <= -self.monthly_loss_percent_stop_trade:
                monthly_stop_reason = "loss"
                monthly_stop_value = profit_percent_per_month
                needed_to_tactical = self.tactical_balance - balance
                if needed_to_tactical > 0 and save_money >= needed_to_tactical:
                    balance += needed_to_tactical
                    save_money -= needed_to_tactical
                    used_save_money_for_monthly_loss = True

            if profit_percent_per_month <= -self.monthly_loss_percent_stop_trade:
                cooldown_until_index = i
                trade_power = False    # off

            #     self.just_one_time = True
            # if you want to make cooldown for a time
            # elif profit_percent_per_month < -10:
            #     if self.just_one_time == True:
            #         cooldown_until_index = i + 4 * 24 * 10
            #         self.just_one_time = False
        if self.monthly_profit_close_filter == False and self.monthly_loss_close_filter == False:
            if balance >= self.tactical_balance * 1.08:
                self.tactical_balance = balance

        # ---- save money ----
        # Recovery trigger must use active portfolio capital (free balance + other open margins),
        # not only free balance; otherwise multi-position mode withdraws too early.
        if trade_power and (not used_save_money_for_monthly_loss):
            save_money_recover_amount_pct = 100 - self.save_money_recover_trigger_pct
            active_capital = balance + remaining_open_margin
            recover_trigger_capital = self.tactical_balance * self.save_money_recover_trigger_pct / 100
            recover_amount = self.tactical_balance * save_money_recover_amount_pct / 100
            if active_capital < recover_trigger_capital:
                if save_money >= recover_amount:
                    balance += recover_amount
                    save_money -= recover_amount

        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_log_override
        )
        has_other_open_positions_at_close = remaining_open_margin > 0
        log_total_assets = balance + remaining_open_margin + save_money
        log_profit_percent_per_month = (((log_total_assets - save_money) * 100) / log_tactical_balance) - 100
        csv_logger.log_trade(
            trade_id,
            "LONG",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(log_tactical_balance, 2),
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
            has_other_open_positions_at_close
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
            'monthly_stop_reason': monthly_stop_reason,
            'monthly_stop_value': monthly_stop_value,
            'logged_balance_before': logged_balance_before,
            'logged_balance_after': logged_balance_after,
            'days': days,
            'hours': hours,
            'minutes': minutes,
        }
    

    # open short processes
    def open_short(self, i, open_prices, open_times,
                    balance, balance_without_fee,
                    trade_amount_percent, margin_balance):

        entry_price = open_prices[i]

        free_balance_before_open = balance
        free_balance_before_open_no_fee = balance_without_fee

        # ---------- Margin ----------
        if balance >= trade_amount_percent * self.tactical_balance:
            margin = trade_amount_percent * self.tactical_balance
        else:
            margin = balance
        margin = max(0.0, min(margin, balance))
        if margin <= 0:
            return None

        # ---------- Margin No Fee ----------
        if balance_without_fee >= trade_amount_percent * self.tactical_balance:
            margin_no_fee = trade_amount_percent * self.tactical_balance
        else:
            margin_no_fee = balance_without_fee
        margin_no_fee = max(0.0, min(margin_no_fee, balance_without_fee))

        # ---------- Leverage ----------
        # In multi-position mode, free balance drops after each open.
        # Use total active capital (free + locked margin) for leverage safety tiers.
        leverage_ref_balance = margin_balance if margin_balance is not None else balance
        leverage_ref_balance = max(0.0, leverage_ref_balance)
        if leverage_ref_balance <= self.tactical_balance * self.safe_leverage_balance_pct_low / 100:
            leverage = self.safe_leverage_low  # 2 low
        elif leverage_ref_balance <= self.tactical_balance * self.safe_leverage_balance_pct_med / 100:
            leverage = self.safe_leverage_med  # 3 med
        elif leverage_ref_balance <= self.tactical_balance * self.safe_leverage_balance_pct_high / 100:
            leverage = self.safe_leverage_high # 4 high
        else:
            leverage = self.leverage    # = 10

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
            'balance_before_trade': free_balance_before_open,
            'balance_before_trade_no_fee': free_balance_before_open_no_fee,
            'margin': margin,
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
            balance_before_close_snapshot=None, balance_before_close_no_fee_snapshot=None,
            balance_before_log_override=None):

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
        capital_before_trade = free_balance_before_close + margin
        profit_percent = self._safe_percent(profit, capital_before_trade)
        total_assets = balance + remaining_open_margin + save_money
        profit_percent_per_month = (((total_assets - save_money) * 100) / self.tactical_balance) - 100
        pnl_percent = self._safe_percent(pnl, margin)

        deducting_fee_total += total_fee
        profits_lst.append(profit)
        total_profit_percent += profit_percent
        count_closed_orders += 1

        equity_curve.append(total_assets)
        # ---- calculate max drawdown ----
        peak = max(equity_curve)
        drawdown = (balance + save_money + remaining_open_margin - peak) / peak * 100
        max_drawdown = min(max_drawdown, drawdown)

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
            logged_balance_before, logged_balance_after = self._resolve_csv_balances(
                free_balance_before_close,
                margin,
                profit
            )
            logged_balance_before_no_fee = free_balance_before_close_no_fee + margin_no_fee
            logged_balance_after_no_fee = free_balance_before_close_no_fee + margin_no_fee + pnl_no_fee
            print("Close SHORT at price:", close_price, "$", "| Close Time:", close_time_value, "| leverage:", leverage)
            print("Balance:", round(logged_balance_before, 2), "$", "→", round(logged_balance_after, 2), "$", "| Save Money:", round(save_money, 2), "$")
            print("Balance (no fee):",
                round(logged_balance_before_no_fee, 2), "$", "→", round(logged_balance_after_no_fee, 2), "$")
            print("pnl:", round(pnl, 2), "$ |", round(pnl_percent, 2), "% |", "Amount:", round(margin), "$")
            print("fee:", round(total_fee, 2), "$")
            print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
            print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
            print("-" * 90)

        used_save_money_for_monthly_loss = False
        monthly_stop_reason = None
        monthly_stop_value = None
        log_tactical_balance = self.tactical_balance

        # stop trade if we got monthly target profit
        # Apply monthly actions only after the last close in a batch.
        if trade_power and remaining_open_margin <= 0 and self.monthly_profit_close_filter == True :
            if profit_percent_per_month >= self.monthly_profit_percent_stop_trade:
                monthly_stop_reason = "profit"
                monthly_stop_value = profit_percent_per_month
                self.tactical_balance = self.tactical_balance + (self.tactical_balance * self.monthly_compound / 100)
                monthly_surplus = balance - self.tactical_balance
                if monthly_surplus > 0:
                    save_money += monthly_surplus
                balance = self.tactical_balance
                cooldown_until_index = i
                trade_power = False    # off

        # stop trade if we got monthly max loss
        if trade_power and remaining_open_margin <= 0 and self.monthly_loss_close_filter == True:
            if profit_percent_per_month <= -self.monthly_loss_percent_stop_trade:
                monthly_stop_reason = "loss"
                monthly_stop_value = profit_percent_per_month
                needed_to_tactical = self.tactical_balance - balance
                if needed_to_tactical > 0 and save_money >= needed_to_tactical:
                    balance += needed_to_tactical
                    save_money -= needed_to_tactical
                    used_save_money_for_monthly_loss = True

            if profit_percent_per_month <= -self.monthly_loss_percent_stop_trade:
                cooldown_until_index = i
                trade_power = False    # off

            #     self.just_one_time = True
            # if you want to make cooldown for a time
            # elif profit_percent_per_month < -10:
            #     if self.just_one_time == True:
            #         cooldown_until_index = i + 4 * 24 * 10
            #         self.just_one_time = False

        if self.monthly_profit_close_filter == False and self.monthly_loss_close_filter == False:
            if balance >= self.tactical_balance * 1.08:
                self.tactical_balance = balance

        # ---- save money ----
        # Recovery trigger must use active portfolio capital (free balance + other open margins),
        # not only free balance; otherwise multi-position mode withdraws too early.
        if trade_power and (not used_save_money_for_monthly_loss):
            save_money_recover_amount_pct = 100 - self.save_money_recover_trigger_pct
            active_capital = balance + remaining_open_margin
            recover_trigger_capital = self.tactical_balance * self.save_money_recover_trigger_pct / 100
            recover_amount = self.tactical_balance * save_money_recover_amount_pct / 100
            if active_capital < recover_trigger_capital:
                if save_money >= recover_amount:
                    balance += recover_amount
                    save_money -= recover_amount

        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            free_balance_before_close,
            margin,
            profit,
            balance_before_log_override
        )
        has_other_open_positions_at_close = remaining_open_margin > 0
        log_total_assets = balance + remaining_open_margin + save_money
        log_profit_percent_per_month = (((log_total_assets - save_money) * 100) / log_tactical_balance) - 100
        csv_logger.log_trade(
            trade_id,
            "SHORT",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(log_tactical_balance, 2),
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
            has_other_open_positions_at_close
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
            'monthly_stop_reason': monthly_stop_reason,
            'monthly_stop_value': monthly_stop_value,
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
        balance_before_close_snapshot=None, balance_before_close_no_fee_snapshot=None,
        balance_before_log_override=None
    ):

        liquid_price_long = entry_price * (1 - 1 / leverage)

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

        close_price = liquid_price_long
        close_time_value = close_times[i]
        if balance_before_close_snapshot is None:
            balance_before_close = balance
        else:
            balance_before_close = balance_before_close_snapshot
        if balance_before_close_no_fee_snapshot is None:
            balance_before_close_no_fee = balance_without_fee
        else:
            balance_before_close_no_fee = balance_before_close_no_fee_snapshot

        profit = -margin
        capital_before_trade = balance_before_close + margin
        profit_percent = self._safe_percent(profit, capital_before_trade)
        pnl_percent = -100
        total_fee_liq = 0

        # Margin has already been deducted at open-time, so free balance stays unchanged on liquidation.
        balance = balance_before_close
        balance_without_fee = balance_before_close_no_fee

        deducting_fee_total += total_fee_liq
        count_closed_orders += 1
        total_losses += 1
        total_long += 1
        total_liquids += 1

        total_assets = balance + remaining_open_margin + save_money
        profit_percent_per_month = (((total_assets - save_money) * 100) / self.tactical_balance) - 100
        equity_curve.append(total_assets)
        peak = max(equity_curve)
        drawdown = (total_assets - peak) / peak * 100
        max_drawdown = min(max_drawdown, drawdown)

        days, hours, minutes = trade_duration(open_time_value, close_time_value)

        if self.verbose:
            print("\U0001F534 LONG LIQUIDATED at price:", round(close_price, 2),
                "| Time:", close_time_value)

        # -------- CSV LOG --------
        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            balance_before_close,
            margin,
            profit,
            balance_before_log_override
        )
        has_other_open_positions_at_close = remaining_open_margin > 0
        csv_logger.log_trade(
            trade_id,
            "LONG_LIQUIDATED",           # Trade type
            open_time_value,             # Open Time
            close_time_value,            # Close Time
            entry_price,                 # Entry Price
            close_price,                 # Close Price
            round(self.tactical_balance, 2),
            round(total_assets, 2),
            round(logged_balance_before, 2),  # Balance before close
            round(logged_balance_after, 2),            # Balance after trade
            round(margin, 2),             # Margin used
            leverage,                    # Leverage
            trade_amount_percent,        # Trade amount percent
            round(profit, 2),             # Profit in $
            round(profit_percent, 2),     # Profit %
            round(pnl_percent, 2),        # PnL %
            round(total_fee_liq, 4),      # Total Fee
            days,
            hours,
            minutes,
            save_money,
            profit_percent_per_month,
            has_other_open_positions_at_close
        )

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
        balance_before_close_snapshot=None, balance_before_close_no_fee_snapshot=None,
        balance_before_log_override=None
    ):

        liquid_price_short = entry_price * (1 + 1 / leverage)

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

        close_price = liquid_price_short
        close_time_value = close_times[i]
        if balance_before_close_snapshot is None:
            balance_before_close = balance
        else:
            balance_before_close = balance_before_close_snapshot
        if balance_before_close_no_fee_snapshot is None:
            balance_before_close_no_fee = balance_without_fee
        else:
            balance_before_close_no_fee = balance_before_close_no_fee_snapshot

        profit = -margin
        capital_before_trade = balance_before_close + margin
        profit_percent = self._safe_percent(profit, capital_before_trade)
        pnl_percent = -100
        total_fee_liq = 0

        # Margin has already been deducted at open-time, so free balance stays unchanged on liquidation.
        balance = balance_before_close
        balance_without_fee = balance_before_close_no_fee

        deducting_fee_total += total_fee_liq
        count_closed_orders += 1
        total_losses += 1
        total_short += 1
        total_liquids += 1

        total_assets = balance + remaining_open_margin + save_money
        profit_percent_per_month = (((total_assets - save_money) * 100) / self.tactical_balance) - 100
        equity_curve.append(total_assets)
        peak = max(equity_curve)
        drawdown = (total_assets - peak) / peak * 100
        max_drawdown = min(max_drawdown, drawdown)

        days, hours, minutes = trade_duration(open_time_value, close_time_value)

        if self.verbose:
            print("\U0001F534 SHORT LIQUIDATED at price:", round(close_price, 2),
                "| Time:", close_time_value)

        # -------- CSV LOG --------
        logged_balance_before, logged_balance_after = self._resolve_csv_balances(
            balance_before_close,
            margin,
            profit,
            balance_before_log_override
        )
        has_other_open_positions_at_close = remaining_open_margin > 0
        csv_logger.log_trade(
            trade_id,
            "SHORT_LIQUIDATED",          # Trade type
            open_time_value,             # Open Time
            close_time_value,            # Close Time
            entry_price,                 # Entry Price
            close_price,                 # Close Price
            round(self.tactical_balance, 2),
            round(total_assets, 2),
            round(logged_balance_before, 2),  # Balance before close
            round(logged_balance_after, 2),            # Balance after trade
            round(margin, 2),             # Margin used
            leverage,                    # Leverage
            trade_amount_percent,        # Trade amount percent
            round(profit, 2),             # Profit in $
            round(profit_percent, 2),     # Profit %
            round(pnl_percent, 2),        # PnL %
            round(total_fee_liq, 4),      # Total Fee
            days,
            hours,
            minutes,
            save_money,
            profit_percent_per_month,
            has_other_open_positions_at_close
        )

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

