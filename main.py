import pandas as pd

def fetch_closing_prices(start: int, end: int):
    df = pd.read_csv('btc_15m_data.csv')
    data = df.iloc[start:end]
    closes_orders_lst = []

    for index, row in data.iterrows():
        closes_orders_lst.append(row['Close'])

    return closes_orders_lst

# for price in fetch_closing_prices(244944,244994):


def get_MA(period):
    closes_orders_ma_lst = []
    close_prices = fetch_closing_prices(244944,244994)
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


print(get_MA(9))
    