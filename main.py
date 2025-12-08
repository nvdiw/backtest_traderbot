import pandas as pd

# start = 244944
# end = 244994

balance = 1000

start = 244994
end = 245602
is_order_open = False



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

    return {"Open time": open_times_lst, 
            "Close time": close_times_lst,
            "Open": opens_prices_lst,
            "Close": closes_prices_lst
            }

all_data = fetch_all_data(start, end)
close_prices = all_data["Close"]

def get_MA(period):
    closes_orders_ma_lst = []
    ma_lst = []
    for price in close_prices:
        closes_orders_ma_lst.append(price)

        if len(closes_orders_ma_lst) < period:
            ma = None
            ma_lst.append(ma)

        if len(closes_orders_ma_lst) >= period:
            ma = sum(closes_orders_ma_lst) / period
            ma_lst.append(round(ma , 2))
            closes_orders_ma_lst.pop(0)

    return ma_lst

def open_long(index):
    global is_order_open
    if is_order_open == False:
        is_order_open = True
        open_price = close_prices[index]
        print("Open Long at price: ", open_price)
        return open_price

def close_long(index):
    global is_order_open
    if is_order_open == True:
        is_order_open = False
        close_price = close_prices[index]
        print("Close Long at price: ", close_price)
        return close_price

def when_open_order():
    global balance
    
    ma_9 = get_MA(9)
    ma_21 = get_MA(21)
    signals = []
    order = []
    profits = []
    for i in range(len(close_prices)):
        if ma_9[i] is None or ma_21[i] is None:
            signals.append("No Signal")
            continue

        if ma_9[i] > ma_21[i]:
            signals.append("Buy")
            open_order = open_long(i)
            if open_order is not None:
                open_order_price = balance / open_order
                order.append("open is " + str(open_order))
                oo = open_order

        elif ma_9[i] < ma_21[i]:
            signals.append("Sell")
            close_order = close_long(i)
            if close_order is not None:
                close_order_price = open_order_price * close_order
                balance = close_order_price
                order.append("close is " + str(close_order))
                co = close_order
                profit = co - oo
                profits.append(round(profit, 2))

        else:
            signals.append("Hold")

    # print(order)
    print("Final Balance: ", round(balance, 2))
    print("Profits: ", profits)
    print("Total Profit: ", sum(profits))
    return signals

# print(when_open_order())
when_open_order()