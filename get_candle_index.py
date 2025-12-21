import pandas as pd

# open the csv file
df = pd.read_csv("./data_candle/btc_15m_data_2018_to_2025.csv", parse_dates=["Open time"])

# get candle index
def get_candle_index(date, time=None):
    """
    date:
        - str  -> "YYYY-MM-DD"
        - tuple -> ("YYYY-MM-DD", "YYYY-MM-DD")
    time:
        - None
        - str -> "HH:MM"
        - tuple -> ("HH:MM", "HH:MM")

    return:
        - int (single index)
        - tuple (start_index, end_index)
    """

    def _to_index(d, t=None):
        if t:
            target = pd.to_datetime(f"{d} {t}")
        else:
            target = pd.to_datetime(d)
        return df["Open time"].searchsorted(target)

    # ===== RANGE MODE =====
    if isinstance(date, tuple):
        start_date, end_date = date

        if isinstance(time, tuple):
            start_time, end_time = time
        else:
            start_time = end_time = time

        start_idx = _to_index(start_date, start_time)
        end_idx = _to_index(end_date, end_time)

        return start_idx, end_idx

    # ===== SINGLE MODE =====
    return _to_index(date, time)


# get month start indices
def get_month_start_indices(start_idx: int, end_idx: int, just_index : bool):
    """
    Returns a list of (YYYY-MM, candle_index) for the first candle of each month
    inside [start_idx, end_idx)
    """

    month_starts = []
    seen_months = set()

    for i in range(start_idx, end_idx):
        ts = df["Open time"].iloc[i]
        month_key = ts.strftime("%Y-%m")

        if month_key not in seen_months:
            seen_months.add(month_key)
            month_starts.append((month_key, i))

    if just_index:
        lst_month_starts = []
        for m, index in month_starts:
            lst_month_starts.append(index)
        return lst_month_starts
    else:
        return month_starts


# ========== test ==========
# print(get_candle_index("2018-01-01"))         # 0
# print(get_candle_index("2018-01-01", "00:15"))  # 1
# print(get_candle_index("2025-01-01"))         # 244942
# print(get_candle_index("2025-01-01", "01:00"))  # 244946 ----> 244942 + 4
# print(get_candle_index("2000-01-01", "23:45"))  # 0   because isn't exist show first rows index "2000-01-01"
# print(get_candle_index("2050-01-01"))         # 278732 because isn't exist show first rows index "2050-01-01"
# # update
# start, end = get_candle_index(("2025-08-01","2025-12-01"))
# print(start, "|", end)          # 265294 | 277006
# start, end = get_candle_index(("2025-08-01","2025-12-01"), (None, "00:15"))
# print(start, "|", end)          # 265294 | 277007

# lst_month_start_indices = get_month_start_indices(start, end, just_index = False) # False
# print(lst_month_start_indices)  # [('2025-08', 265294), ('2025-09', 268270), ('2025-10', 271150), ('2025-11', 274126), ('2025-12', 277006)]
# lst_month_start_indices = get_month_start_indices(start, end, just_index = True) # True
# print(lst_month_start_indices)  # [265294, 268270, 271150, 274126, 277006]