# NOTE: Strategy executes ONLY on candle Open prices

import pandas as pd

# 2025/01/01 first 15m candle of btc_15m_data.csv is: 244944 <--- start
# 2025/03/01 15m candle of btc_15m_data.csv is: 250608 <--- 2025/03/01
# 2025/06/01 15m candle of btc_15m_data.csv is: 259440 <--- 2025/06/01
# the last last 15m candle of btc_15m_data.csv is: 277581 <--- end

start = 244944
end = 277581

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


# Calculate Moving Average
def get_MA(period):
    closes_orders_ma_lst = []
    ma_lst = []
    for price in open_prices:
        closes_orders_ma_lst.append(price)

        if len(closes_orders_ma_lst) < period:
            ma = None
            ma_lst.append(ma)

        if len(closes_orders_ma_lst) >= period:
            ma = sum(closes_orders_ma_lst) / period
            ma_lst.append(round(ma , 2))
            closes_orders_ma_lst.pop(0)

    return ma_lst


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


# Open Long Position
def open_long(index):
    global current_position
    if current_position is None:
        current_position = "long"
        return open_prices[index]
    return None


# open Short Position
def open_short(index):
    global current_position
    if current_position is None:
        current_position = "short"
        return open_prices[index]
    return None


# Close Long Position
def close_long(index):
    global current_position
    if current_position == "long":
        current_position = None
        return open_prices[index]
    return None


# close Short Position
def close_short(index):
    global current_position
    if current_position == "short":
        current_position = None
        return open_prices[index]
    return None


# Main Trading Logic
def execute_trading_logic():

    global current_position

    balance = 1000
    balance_without_fee = balance
    first_balance = balance

    fee_rate = 0.0005  # 0.05%

    deducting_fee_total = 0
    count_closed_orders = 0
    profits_lst = []

    current_position = None
    entry_price = None
    position_size = None
    position_size_no_fee = None
    balance_before_trade = None
    balance_before_trade_no_fee = None
    open_time_value = None

    ma_21 = get_MA(15)
    ma_50 = get_MA(45)
    ma_100 = get_MA(100)
    ma_200 = get_MA(200)
    for i in range(len(open_prices)):

        if ma_21[i] is None or ma_50[i] is None or ma_100[i] is None or ma_200[i] is None:
            continue
        

        ma_distance = abs(ma_21[i] - ma_50[i]) / ma_50[i]


        if ma_100[i] >= ma_200[i]:
            # ===================== OPEN LONG =====================
            if ma_21[i] > ma_50[i] and current_position is None and ma_distance > 0.002:

                entry_price = open_prices[i]

                position_size = balance / entry_price
                position_size_no_fee = balance_without_fee / entry_price

                balance_before_trade = balance
                balance_before_trade_no_fee = balance_without_fee

                open_time_value = open_times[i]
                current_position = "long"

                print("Open LONG at price:", entry_price, "| Open Time:", open_time_value)

            # ===================== CLOSE LONG =====================
            if ma_21[i] < ma_50[i] and current_position == "long":

                close_price = open_prices[i]

                # -------- WITH FEE --------
                close_value = position_size * close_price
                fee = close_value * fee_rate
                balance = close_value - fee

                # -------- WITHOUT FEE --------
                close_value_no_fee = position_size_no_fee * close_price
                balance_without_fee = close_value_no_fee

                profit = balance - balance_before_trade
                profit_percent = profit * 100 / balance_before_trade

                deducting_fee_total += fee
                profits_lst.append(profit)
                count_closed_orders += 1

                close_time_value = open_times[i]
                days, hours, minutes = trade_duration(open_time_value, close_time_value)

                print("Close LONG at price:", close_price, "| Close Time:", close_time_value)
                print("Balance:", round(balance_before_trade, 2), "→", round(balance, 2))
                print("Balance (no fee):",
                    round(balance_before_trade_no_fee, 2), "→", round(balance_without_fee, 2))
                print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
                print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
                print("-" * 90)

                current_position = None

        if ma_100[i] < ma_200[i]:
            # ===================== OPEN SHORT =====================
            if ma_21[i] < ma_50[i] and current_position is None and ma_distance > 0.002:

                entry_price = open_prices[i]

                position_size = balance / entry_price
                position_size_no_fee = balance_without_fee / entry_price

                balance_before_trade = balance
                balance_before_trade_no_fee = balance_without_fee

                open_time_value = open_times[i]
                current_position = "short"

                print("Open SHORT at price:", entry_price, "| Open Time:", open_time_value)

            # ===================== CLOSE SHORT =====================
            if ma_21[i] > ma_50[i] and current_position == "short":

                close_price = open_prices[i]

                # -------- WITH FEE --------
                profit = position_size * (entry_price - close_price)
                close_value = balance_before_trade + profit
                fee = close_value * fee_rate
                balance = close_value - fee

                # -------- WITHOUT FEE --------
                profit_no_fee = position_size_no_fee * (entry_price - close_price)
                balance_without_fee = balance_before_trade_no_fee + profit_no_fee

                profit = balance - balance_before_trade
                profit_percent = profit * 100 / balance_before_trade

                deducting_fee_total += fee
                profits_lst.append(profit)
                count_closed_orders += 1

                close_time_value = open_times[i]
                days, hours, minutes = trade_duration(open_time_value, close_time_value)

                print("Close SHORT at price:", close_price, "| Close Time:", close_time_value)
                print("Balance:", round(balance_before_trade, 2), "→", round(balance, 2))
                print("Balance (no fee):",
                    round(balance_before_trade_no_fee, 2), "→", round(balance_without_fee, 2))
                print("Profit:", round(profit, 2), "$ |", round(profit_percent, 2), "%")
                print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
                print("-" * 90)

                current_position = None

    total_profit_percent = balance * 100 / first_balance - 100

    print("✅ BACKTEST FINISHED")
    print("Closed Trades:", count_closed_orders)
    print("Final Balance:", round(balance, 2))
    print("Final Balance (No Fee):", round(balance_without_fee, 2))
    print("Total Fees Paid:", round(deducting_fee_total, 2))
    print("Fee Compounding Impact:",
          round(balance_without_fee - balance - deducting_fee_total, 2), "$")
    print("Total Profit:", round(sum(profits_lst), 2), "$")
    print("Total Profit Percent:", round(total_profit_percent, 2), "%")


# Run the trading logic
execute_trading_logic()