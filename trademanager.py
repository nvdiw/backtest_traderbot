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
    def __init__(self, csv_logger, first_balance, monthly_profit_percent_stop_trade,tactical_balance):
        self.csv_logger = csv_logger
        self.first_balance = first_balance
        self.monthly_profit_percent_stop_trade = monthly_profit_percent_stop_trade
        self.tactical_balance = tactical_balance
    # open long processes
    def open_long(self, i, open_prices, open_times,
                    balance, balance_without_fee, first_balance,
                    trade_amount_percent, total_balance, leverage):

        entry_price = open_prices[i]

        balance_before_trade = balance
        balance_before_trade_no_fee = balance_without_fee

        # ---------- Margin ----------
        if balance >= 50 / 100 * first_balance:
            margin = 50 / 100 * first_balance
        else:
            margin = balance * trade_amount_percent
        
        # ---------- Leverage ----------
        if total_balance <= first_balance * 90 / 100:
            leverage = 3
        else:
            leverage = 5

        position_value = margin * leverage
        position_size = position_value / entry_price

        margin_no_fee = balance_without_fee * trade_amount_percent
        position_value_no_fee = margin_no_fee * leverage
        position_size_no_fee = position_value_no_fee / entry_price

        # update balance after allocating margin
        balance -= margin
        balance_without_fee -= margin_no_fee

        # update open time and current position
        open_time_value = open_times[i]
        current_position = "long"

        print("Open LONG at price:", entry_price, "$", "| Open Time:", open_time_value, "| leverage:", leverage)

        return {
            'entry_price': entry_price,
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'balance_before_trade': balance_before_trade,
            'balance_before_trade_no_fee': balance_before_trade_no_fee,
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
                balance_before_trade, balance_before_trade_no_fee,
                deducting_fee_total, profits_lst, total_profit_percent,
                count_closed_orders, equity_curve,
                max_drawdown, total_wins, total_wins_long, total_losses,
                total_long, cooldown_after_big_pnl, leverage,
                cooldown_until_index, open_time_value, csv_logger, trade_amount_percent, profit_percent_per_month,
                save_money, trade_power):

        close_price = open_prices[i]

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

        # profit after fee
        profit = balance - balance_before_trade
        profit_percent = profit * 100 / balance_before_trade
        profit_percent_per_month = ((balance * 100) / self.tactical_balance) - 100
        pnl_percent = (pnl / margin) * 100

        deducting_fee_total += total_fee
        profits_lst.append(profit)
        total_profit_percent += profit_percent
        count_closed_orders += 1

        equity_curve.append(balance)
        # ---- calculate max drawdown ----
        peak = max(equity_curve)
        drawdown = (balance - peak) / peak * 100
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
        pnl_percent_without_leverage = ((pnl / margin) * 100 ) / leverage
        if pnl_percent_without_leverage >= 3 or pnl_percent_without_leverage <= -2:
            cooldown_until_index = i + cooldown_after_big_pnl
            print(f"🟡 Cooldown Activated (LONG) until candle index {cooldown_until_index}")

        close_time_value = open_times[i]
        days, hours, minutes = trade_duration(open_time_value, close_time_value)


        print("Close LONG at price:", close_price, "$", "| Close Time:", close_time_value, "| leverage:", leverage)
        print("Balance:", round(balance_before_trade, 2), "$", "→", round(balance, 2), "$", "| Save Money:", round(save_money, 2), "$")
        print("Balance (no fee):",
            round(balance_before_trade_no_fee, 2), "$", "→", round(balance_without_fee, 2), "$")
        print("pnl:", round(pnl, 2), "$ |", round(pnl_percent, 2), "% |" , "Amount:", round(margin), "$")
        print("fee:", round(total_fee, 2), "$")
        print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
        print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
        print("-" * 90)

        csv_logger.log_trade(
            "LONG",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(balance_before_trade, 2),
            round(balance, 2),
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
            save_money,
            profit_percent_per_month
        )

        # ---- save money ----
        if balance < self.tactical_balance * 75 / 100:
            if save_money >= self.tactical_balance * 25 / 100:
                balance += self.tactical_balance * 25 / 100
                save_money -= self.tactical_balance * 25 / 100

        # stop trade if we got 6% for this month
        if profit_percent_per_month >= self.monthly_profit_percent_stop_trade:
            self.tactical_balance = self.tactical_balance + (self.tactical_balance * 2.5 / 100)
            save_money += balance - self.tactical_balance
            balance = self.tactical_balance
            cooldown_until_index = i
            trade_power = False    # off

        current_position = None

        return {
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'deducting_fee_total': deducting_fee_total,
            'profits_lst': profits_lst,
            'total_profit_percent': total_profit_percent,
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
            'save_money' : save_money
        }
    
    # open short processes
    def open_short(self, i, open_prices, open_times,
                    balance, balance_without_fee, first_balance,
                    trade_amount_percent, total_balance, leverage):

        entry_price = open_prices[i]

        balance_before_trade = balance
        balance_before_trade_no_fee = balance_without_fee

        # ---------- LVR Margin ----------
        if balance >= 50 / 100 * first_balance:
            margin = 50 / 100 * first_balance
        else:
            margin = balance * trade_amount_percent

        # ---------- Leverage ----------
        if total_balance <= first_balance * 90 / 100:
            leverage = 3
        else:
            leverage = 5

        position_value = margin * leverage
        position_size = position_value / entry_price

        margin_no_fee = balance_without_fee * trade_amount_percent
        position_value_no_fee = margin_no_fee * leverage
        position_size_no_fee = position_value_no_fee / entry_price

        # update balance after allocating margin
        balance -= margin
        balance_without_fee -= margin_no_fee

        # update open time and current position
        open_time_value = open_times[i]
        current_position = "short"

        print("Open SHORT at price:", entry_price, "$", "| Open Time:", open_time_value, "| leverage:", leverage)

        return {
            'entry_price': entry_price,
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'balance_before_trade': balance_before_trade,
            'balance_before_trade_no_fee': balance_before_trade_no_fee,
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
            balance_before_trade, balance_before_trade_no_fee,
            deducting_fee_total, profits_lst, total_profit_percent,
            count_closed_orders, equity_curve,
            max_drawdown, total_wins, total_wins_short, total_losses,
            total_short, cooldown_after_big_pnl, leverage,
            cooldown_until_index, open_time_value, csv_logger, trade_amount_percent, profit_percent_per_month,
            save_money, trade_power):

        close_price = open_prices[i]

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

        # profit after fee
        profit = balance - balance_before_trade
        profit_percent = profit * 100 / balance_before_trade
        profit_percent_per_month = ((balance * 100) / self.tactical_balance) - 100
        pnl_percent = (pnl / margin) * 100

        deducting_fee_total += total_fee
        profits_lst.append(profit)
        total_profit_percent += profit_percent
        count_closed_orders += 1

        equity_curve.append(balance)
        # ---- calculate max drawdown ----
        peak = max(equity_curve)
        drawdown = (balance - peak) / peak * 100
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
        pnl_percent_without_leverage = ((pnl / margin) * 100) / leverage
        if pnl_percent_without_leverage >= 3 or pnl_percent_without_leverage <= -2:
            cooldown_until_index = i + cooldown_after_big_pnl
            print(f"🟡 Cooldown Activated (SHORT) until candle index {cooldown_until_index}")

        close_time_value = open_times[i]
        days, hours, minutes = trade_duration(open_time_value, close_time_value)


        print("Close SHORT at price:", close_price, "$", "| Close Time:", close_time_value, "| leverage:", leverage)
        print("Balance:", round(balance_before_trade, 2), "$", "→", round(balance, 2), "$", "| Save Money:", round(save_money, 2), "$")
        print("Balance (no fee):",
            round(balance_before_trade_no_fee, 2), "$", "→", round(balance_without_fee, 2), "$")
        print("pnl:", round(pnl, 2), "$ |", round(pnl_percent, 2), "% |", "Amount:", round(margin), "$")
        print("fee:", round(total_fee, 2), "$")
        print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
        print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
        print("-" * 90)

        csv_logger.log_trade(
            "SHORT",
            open_time_value,
            close_time_value,
            entry_price,
            close_price,
            round(balance_before_trade, 2),
            round(balance, 2),
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
            save_money,
            profit_percent_per_month
        )

        # ---- save money ----
        if balance < self.tactical_balance * 75 / 100:
            if save_money >= self.tactical_balance * 25 / 100:
                balance += self.tactical_balance * 25 / 100
                save_money -= self.tactical_balance * 25 / 100

        # stop trade if we got 6% for this month
        if profit_percent_per_month >= self.monthly_profit_percent_stop_trade:
            self.tactical_balance = self.tactical_balance + (self.tactical_balance * 2.5 / 100)
            save_money += balance - self.tactical_balance
            balance = self.tactical_balance
            cooldown_until_index = i
            trade_power = False    # off
            
        current_position = None

        return {
            'balance': balance,
            'balance_without_fee': balance_without_fee,
            'deducting_fee_total': deducting_fee_total,
            'profits_lst': profits_lst,
            'total_profit_percent': total_profit_percent,
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
            'save_money' : save_money
        }