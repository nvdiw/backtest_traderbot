# NOTE: Strategy executes ONLY on candle Open prices

import pandas as pd

# 2025/01/01 first 15m candle of btc_15m_data.csv is: 244944 <--- start
# 2025/03/01 15m candle of btc_15m_data.csv is: 250608 <--- 2025/03/01
# 2025/06/01 15m candle of btc_15m_data.csv is: 259440 <--- 2025/06/01
# the last last 15m candle of btc_15m_data.csv is: 277581 <--- end

start = 244944
end = 277581

is_order_open = False

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

# Open Long Position
def open_long(index):
    global is_order_open
    if is_order_open == False:
        is_order_open = True
        open_price = open_prices[index]
        # print("Open Long at price: ", open_price)
        return open_price
    else:
        return None

# Close Long Position
def close_long(index):
    global is_order_open
    if is_order_open == True:
        is_order_open = False
        close_price = open_prices[index]
        # print("Close Long at price: ", close_price)
        return close_price
    else:
        return None

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

    balance = 1000
    balance_without_fee = 1000
    ma_9 = get_MA(15)
    ma_21 = get_MA(32)
    signals = []
    order = []
    profits = []
    deducting_fee_total = 0
    count_closed_orders = 0

    for i in range(len(open_prices)):
        if ma_9[i] is None or ma_21[i] is None:
            signals.append("No Signal")
            continue

        if ma_9[i] > ma_21[i]:
            signals.append("Buy")
            open_order = open_long(i)
            if open_order is not None:
                open_order_price = (balance * 1) / open_order
                open_order_price_without_fee = (balance_without_fee * 1) / open_order
                open_time_value = open_times[i]
                order.append("open is " + str(open_order))
                
                print("Open Long at price:  ", open_order , " | Open Time:  ", open_time_value)
                # print("your balance is:", round(balance, 2))
                

        elif ma_9[i] < ma_21[i]:
            signals.append("Sell")
            close_order = close_long(i)
            if close_order is not None:

                count_closed_orders += 1

                last_balance = balance
                close_order_price = open_order_price * close_order / 1
                close_order_price_without_fee = open_order_price_without_fee * close_order / 1
                fee = close_order_price * 0.0005   # 0.05%
                balance = close_order_price - fee
                balance_without_fee = close_order_price_without_fee
                deducting_fee_total += fee
                order.append("close is " + str(close_order))
                profit = balance - last_balance
                profit_percent = balance * 100 / last_balance - 100
                profits.append(profit)
                # close_time_value = close_times[i]               #<----- maybe bug here
                close_time_value = open_times[i]                  #<----- maybe bug here

                days, hours, minutes = trade_duration(open_time = open_time_value, close_time= close_time_value)

                
                print("Close Long at price: ", close_order , " | Close Time: ", close_time_value)
                print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")
                print("balance:", round(last_balance, 2), "| new balance is:", round(balance, 2) ,
                       " | Profit: ", round(profit, 2), "$" , " | Profit Percent: ", round(profit_percent, 2), "%")
                print("Deducting Fee for this order: ", round(fee, 3), "$")
                
                print("--------------------------------------------------------------------------------------")

        else:
            signals.append("Hold")

    # footer information
    print("count closed orders is : ", count_closed_orders)
    print("Final Balance: ", round(balance, 2))
    print("balance without fee is: ", round(balance_without_fee, 2), "$")
    print("Total Deducting Fee: ", round(deducting_fee_total, 2))
    print("Total Profit: ", round(sum(profits), 2))
    print("Fee compounding impact:",
      round(balance_without_fee - deducting_fee_total - balance, 2), "$")

    # print("Orders: " + str(order))
    # print("Profits: ", profits)
    # return signals

# Run the trading logic
execute_trading_logic()