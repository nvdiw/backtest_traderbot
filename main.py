import pandas as pd

start = 244944
end = 245602

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

# Main Trading Logic
def when_open_order():

    balance = 1000
    ma_9 = get_MA(15)
    ma_21 = get_MA(45)
    signals = []
    order = []
    profits = []
    for i in range(len(open_prices)):
        if ma_9[i] is None or ma_21[i] is None:
            signals.append("No Signal")
            continue

        if ma_9[i] > ma_21[i]:
            signals.append("Buy")
            open_order = open_long(i)
            if open_order is not None:
                open_order_price = (balance * 1) / open_order
                order.append("open is " + str(open_order))
                oo = open_order

                open_time_value = open_times[i]
                print("Open Long at price: ", open_order , " | Open Time: ", open_time_value)
                print("your balance is:", round(balance, 2))

        elif ma_9[i] < ma_21[i]:
            signals.append("Sell")
            close_order = close_long(i)
            if close_order is not None:
                close_order_price = open_order_price * close_order / 1
                balance = close_order_price
                order.append("close is " + str(close_order))
                co = close_order
                profit = co - oo
                profits.append(round(profit, 2))

                close_time_value = close_times[i]
                print("Close Long at price: ", close_order , " | Close Time: ", close_time_value)
                print("your balance is:", round(balance, 2) , " | Profit: ", round(profit, 2))
                print("-----------------------------------------------------------------------------")

        else:
            signals.append("Hold")
    # print("Orders: " + str(order))


    print("Final Balance: ", round(balance, 2))
    print("Profits: ", profits)
    print("Total Profit: ", sum(profits))
    return signals

# Run the trading logic
when_open_order()