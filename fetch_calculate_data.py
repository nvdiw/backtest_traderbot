import pandas as pd

# Fetch data from CSV file
def fetch_all_data(start: int, end: int):
    """Load only the required candle window from CSV (start:end)."""
    if start is None or end is None or end <= start:
        return None

    rows_to_read = end - start
    data = pd.read_csv(
        './data_candle/btc_15m_data_2018_to_2026.csv',
        skiprows=range(1, start + 1),
        nrows=rows_to_read,
        usecols=['Open time', 'Close time', 'Open', 'Close', 'Low', 'High', 'Volume'],
    )

    return {
        "Open time": data['Open time'].tolist(),
        "Close time": data['Close time'].tolist(),
        "Open": data['Open'].to_numpy(dtype=float),
        "Close": data['Close'].to_numpy(dtype=float),
        "Low": data['Low'].to_numpy(dtype=float),
        "High": data['High'].to_numpy(dtype=float),
        "Volume": data['Volume'].to_numpy(dtype=float)
    }


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