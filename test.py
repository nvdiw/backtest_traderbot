import pandas as pd

start = 244994
end = 245102

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


x = fetch_all_data(0, 9)

print(x["Open time"][0])