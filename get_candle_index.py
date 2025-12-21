import pandas as pd

# open the csv file
df = pd.read_csv("./data_candle/btc_15m_data_2018_to_2025.csv", parse_dates=["Open time"])

def get_candle_index(date, time=None):
    """
    date: str, format "YYYY-MM-DD"
    time: str or None, format "HH:MM" (optional)
    return: int or None / index of the candle
    """
    # to datetime
    if time:
        target = pd.to_datetime(f"{date} {time}")
    else:
        target = pd.to_datetime(date)

    # filtering
    mask = df["Open time"] == target
    if mask.any():
        return df.index[mask][0]
    else:
        return None

# ========== test ==========
# print(get_candle_index("2018-01-01"))         # 0
# print(get_candle_index("2018-01-01", "00:15"))  # 1
# print(get_candle_index("2025-01-01"))         # 244942
# print(get_candle_index("2025-01-01", "01:00"))  # 244946 ----> 244942 + 4
# print(get_candle_index("2025-12-31", "23:45"))  # None (not found)