# NOTE: Strategy executes ONLY on candle Open prices

import pandas as pd

# My Codes :
from trade_csv_logger import TradeCSVLogger
from indicators import get_MA, get_EMA

# 2025/01/01 first 15m candle of btc_15m_data.csv is: 244944 <--- start
# 2025/03/01 15m candle of btc_15m_data.csv is: 250608 <--- 2025/03/01
# 2025/06/01 15m candle of btc_15m_data.csv is: 259440 <--- 2025/06/01
# the last last 15m candle of btc_15m_data.csv is: 277580 <--- end
# 25 oct 2025 00:00 = 273456
# 6 dec 2025 00:00 = 277580



start = 244944
end = 277580

current_position = None  # None | "long" | "short"

# Fetch data from CSV file
def fetch_all_data(start : int, end : int):
    df = pd.read_csv('btc_15m_data.csv')
    data = df.iloc[start:end]

    open_times_lst = []
    close_times_lst = []
    closes_prices_lst = []
    opens_prices_lst = []

    for index, row in data.iterrows():
        open_times_lst.append(row['Open time'])
        close_times_lst.append(row['Close time'])
        opens_prices_lst.append(row['Open'])
        closes_prices_lst.append(row['Close'])

    return {
            "Open time": open_times_lst, 
            "Close time": close_times_lst,
            "Open": opens_prices_lst,
            "Close": closes_prices_lst
            }

all_data = fetch_all_data(start, end)
open_prices = all_data["Open"]
close_prices = all_data["Close"]
open_times = all_data["Open time"]
close_times = all_data["Close time"]

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


# Main Trading Logic
def execute_trading_logic():

    global current_position

    csv_logger = TradeCSVLogger()

    balance = 1000
    balance_without_fee = balance
    first_balance = balance
    leverage = 1
    trade_amount_percent = 1  # 100%
    # save_money = 0

    fee_rate = 0.00025  # 0.05%

    total_wins = 0
    total_losses = 0
    total_long = 0
    total_short = 0
    deducting_fee_total = 0
    count_closed_orders = 0

    max_drawdown = 0
    equity_curve = []
    profits_lst = []

    current_position = None
    entry_price = None
    position_size = None
    position_size_no_fee = None
    balance_before_trade = None
    balance_before_trade_no_fee = None
    open_time_value = None

    first_open_time = open_times[0]
    last_close_time = open_times[-1]

    ema_14 = get_EMA(14, open_prices)
    ma_50 = get_MA(50, open_prices)
    ma_130 = get_MA(130, open_prices)
    ma_200 = get_MA(200, open_prices)


    cooldown_after_big_pnl = 4 * 48  # 4 * x   [x] ---> number of candles per hour
    cooldown_until_index = -1

    ma_distance_threshold = 0.00204  # 0.2٪
    candle_move_threshold = 0.0082 # 0.8٪

    # check data loaded correctly :
        # print(len(open_prices), "candles loaded.")
        # print("len(ema_14):", len(ema_14))
        # print("len(ma_50):", len(ma_50))


    for i in range(len(open_prices)):

        if ema_14[i] is None or ma_50[i] is None or ma_130[i] is None or ma_200[i] is None:
            continue
        
        if i < cooldown_until_index:
            continue
        
        # Calculate MA Distance
        ma_distance = abs(ema_14[i] - ma_50[i]) / ma_50[i]

        # Calculate Distance New Candle Move and Last Candle Move
        if i > 0:
            last_candle_move = abs(open_prices[i] - open_prices[i-1]) / open_prices[i-1]
        else:
            last_candle_move = 0

        # if balance > 1100 :
        #     save_money += 50
        #     balance -= 50

        # ===================== OPEN LONG =====================
        if ma_130[i] >= ma_200[i] and ema_14[i] > ma_50[i] and current_position is None:
            if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                entry_price = open_prices[i]

                balance_before_trade = balance
                balance_before_trade_no_fee = balance_without_fee

                # ---------- LVR Margin ----------
                margin = balance * trade_amount_percent
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

                print("Open LONG at price:", entry_price, "| Open Time:", open_time_value)

        # ===================== CLOSE LONG =====================
        if current_position == "long":
            if (ema_14[i] < ma_50[i]) or (ma_130[i] < ma_200[i]):

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
                pnl_percent = (pnl / margin) * 100

                deducting_fee_total += total_fee
                profits_lst.append(profit)
                count_closed_orders += 1

                equity_curve.append(balance)
                # ---- calculate max drawdown ----
                peak = max(equity_curve)
                drawdown = (balance - peak) / peak * 100
                max_drawdown = min(max_drawdown, drawdown)

                # ---- count wins and losses ----
                if profit_percent > 0:
                    total_wins += 1
                else:
                    total_losses += 1

                # ---- count LONG trades ----
                total_long += 1

                # ---- COOLDOWN AFTER BIG PROFIT ----
                pnl_percent_without_leverage = (pnl / ( balance_before_trade * leverage )) * 100
                if pnl_percent_without_leverage >= 3 or pnl_percent_without_leverage <= -2:
                    cooldown_until_index = i + cooldown_after_big_pnl
                    print(f"🟡 Cooldown Activated (LONG) until candle index {cooldown_until_index}")

                close_time_value = open_times[i]
                days, hours, minutes = trade_duration(open_time_value, close_time_value)


                print("Close LONG at price:", close_price, "| Close Time:", close_time_value)
                print("Balance:", round(balance_before_trade, 2), "→", round(balance, 2))
                print("Balance (no fee):",
                    round(balance_before_trade_no_fee, 2), "→", round(balance_without_fee, 2))
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
                    round(profit, 2),
                    round(profit_percent, 2),
                    round(pnl_percent, 2),
                    round(total_fee, 4),
                    days,
                    hours,
                    minutes
                )


                current_position = None


        # ===================== OPEN SHORT =====================
        if ma_130[i] < ma_200[i] and ema_14[i] < ma_50[i] and current_position is None:
            if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:

                entry_price = open_prices[i]

                balance_before_trade = balance
                balance_before_trade_no_fee = balance_without_fee

                # ---------- LVR Margin ----------
                margin = balance * trade_amount_percent
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

                print("Open SHORT at price:", entry_price, "| Open Time:", open_time_value)

        # ===================== CLOSE SHORT =====================
        if current_position == "short":
            if (ema_14[i] > ma_50[i]) or (ma_130[i] >= ma_200[i]):

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
                pnl_percent = (pnl / margin) * 100

                deducting_fee_total += total_fee
                profits_lst.append(profit)
                count_closed_orders += 1

                equity_curve.append(balance)
                # ---- calculate max drawdown ----
                peak = max(equity_curve)
                drawdown = (balance - peak) / peak * 100
                max_drawdown = min(max_drawdown, drawdown)

                # ---- count wins and losses ----
                if profit_percent > 0:
                    total_wins += 1
                else:
                    total_losses += 1

                # ---- count shorts ----
                total_short += 1

                # ---- COOLDOWN AFTER BIG PROFIT ----
                pnl_percent_without_leverage = (pnl / ( balance_before_trade * leverage )) * 100
                if pnl_percent_without_leverage >= 3 or pnl_percent_without_leverage <= -2:
                    cooldown_until_index = i + cooldown_after_big_pnl
                    print(f"🟡 Cooldown Activated (SHORT) until candle index {cooldown_until_index}")


                close_time_value = open_times[i]
                days, hours, minutes = trade_duration(open_time_value, close_time_value)


                print("Close SHORT at price:", close_price, "| Close Time:", close_time_value)
                print("Balance:", round(balance_before_trade, 2), "→", round(balance, 2))
                print("Balance (no fee):",
                    round(balance_before_trade_no_fee, 2), "→", round(balance_without_fee, 2))
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
                    round(profit, 2),
                    round(profit_percent, 2),
                    round(pnl_percent, 2),
                    round(total_fee, 4),
                    days,
                    hours,
                    minutes
                )

                current_position = None

    # ========== BACKTEST SUMMARY ==========

    if current_position is not None:
        balance += margin  # return margin if position still open
        balance_without_fee += margin_no_fee # return margin if position still open

    total_profit_percent = balance * 100 / first_balance - 100
    days, hours, minutes = trade_duration(first_open_time, last_close_time)
    win_rate = (total_wins / (total_wins + total_losses)) * 100 if (total_wins + total_losses) > 0 else 0


    print("✅ BACKTEST FINISHED")
    print("Closed Trades:", count_closed_orders, "( Longs:", total_long, "| Shorts:", total_short, ")")
    print("Total Wins:", total_wins)
    print("Total Losses:", total_losses)
    print("Final Balance:", round(balance, 2))
    print("Final Balance (No Fee):", round(balance_without_fee, 2))
    print("Total Fees Paid:", round(deducting_fee_total, 2))
    print("Fee Compounding Impact:",
          round(balance_without_fee - balance - deducting_fee_total, 2), "$")
    print("Maximum Drawdown:", round(max_drawdown, 2), "%")
    print(f"Total Duration : {days} days, {hours} hours, {minutes} minutes")
    print("Win Rate:", round(win_rate, 2), "%")
    print("Total Profit:", round(sum(profits_lst), 2), "$")
    print("Total Profit Percent:", round(total_profit_percent, 2), "%")
    # print("saved Money:", save_money, "$")

    csv_logger.save_csv(
    first_balance=first_balance,
    final_balance=balance,
    total_profit=sum(profits_lst),
    total_profit_percent=total_profit_percent,
    total_fee=deducting_fee_total,
    start_time=first_open_time,
    end_time=last_close_time,
    days=days,
    hours=hours,
    minutes=minutes
    )


# Run the trading logic
execute_trading_logic()