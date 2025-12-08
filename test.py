# import pandas as pd

# start = 244994
# end = 245102

# def fetch_all_data(start : int, end : int):
#     df = pd.read_csv('btc_15m_data.csv')
#     data = df.iloc[start:end]

#     open_times_lst = []
#     close_times_lst = []
#     closes_prices_lst = []
#     opens_prices_lst = []

#     for index, row in data.iterrows():
#         open_times_lst.append(row['Open time'])
#         close_times_lst.append(row['Close time'])
#         opens_prices_lst.append(row['Open'])
#         closes_prices_lst.append(row['Close'])

#     return {"Open time": open_times_lst, 
#             "Close time": close_times_lst,
#             "Open": opens_prices_lst,
#             "Close": closes_prices_lst
#             }


# x = fetch_all_data(0, 9)

# print(x["Open time"][0])



def trade_duration(open_time: str, close_time: str):
    # format: YYYY-MM-DD HH:MM:SS.microseconds

    def parse(t):
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


# example
# trade_duration(
#     "2025-12-06 13:00:00.000000",
#     "2025-12-06 19:44:59.999000"
# )

days, hours, minutes = trade_duration(open_time ="2025-12-06 13:00:00.000000", close_time="2025-12-06 19:44:59.999000")
print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")