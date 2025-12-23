import pandas as pd

class Indicator:
    def __init__(self, open_prices, period=None):
        self.open_prices = open_prices
        self.period = period

    # Calculate Moving Average
    def get_MA(self, period):
        closes_orders_ma_lst = []
        ma_lst = []
        for price in self.open_prices:
            closes_orders_ma_lst.append(price)

            if len(closes_orders_ma_lst) < period:
                ma = None
                ma_lst.append(ma)

            if len(closes_orders_ma_lst) >= period:
                ma = sum(closes_orders_ma_lst) / period
                ma_lst.append(round(ma , 2))
                closes_orders_ma_lst.pop(0)

        return ma_lst


    # Calculate Exponential Moving Average
    def get_EMA(self, period):
        ema_lst = []
        k = 2 / (period + 1)
        ema_prev = None

        for price in self.open_prices:

            if ema_prev is None:
                ema = None
            else:
                ema = (price * k) + (ema_prev * (1 - k))
                ema = round(ema, 2)

            ema_lst.append(ema)

            if ema is not None:
                ema_prev = ema

            # مقدار اولیه EMA بعد از پر شدن دوره
            if ema_prev is None and len(ema_lst) == period:
                sma = sum(self.open_prices[:period]) / period
                ema_prev = round(sma, 2)
                ema_lst[-1] = ema_prev

        return ema_lst


    # calculate: ADX --> Average Directional Index
    def get_ADX(self, high, low, close, period=14):

        df = pd.DataFrame({
            "high": high,
            "low": low,
            "close": close
        })

        df["prev_close"] = df["close"].shift(1)
        df["prev_high"] = df["high"].shift(1)
        df["prev_low"] = df["low"].shift(1)

        # ===== True Range =====
        tr_list = [None]
        for i in range(1, len(df)):
            tr = max(
                df["high"].iloc[i] - df["low"].iloc[i],
                abs(df["high"].iloc[i] - df["prev_close"].iloc[i]),
                abs(df["low"].iloc[i] - df["prev_close"].iloc[i])
            )
            tr_list.append(tr)

        df["tr"] = tr_list

        # ===== Directional Movement =====
        plus_dm = [None]
        minus_dm = [None]

        for i in range(1, len(df)):
            up_move = df["high"].iloc[i] - df["prev_high"].iloc[i]
            down_move = df["prev_low"].iloc[i] - df["low"].iloc[i]

            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)

        df["+dm"] = plus_dm
        df["-dm"] = minus_dm

        # ===== Wilder smoothing =====
        df["tr_smooth"] = df["tr"].ewm(alpha=1/period, adjust=False).mean()
        df["+dm_smooth"] = df["+dm"].ewm(alpha=1/period, adjust=False).mean()
        df["-dm_smooth"] = df["-dm"].ewm(alpha=1/period, adjust=False).mean()

        # ===== DI =====
        df["+di"] = 100 * df["+dm_smooth"] / df["tr_smooth"]
        df["-di"] = 100 * df["-dm_smooth"] / df["tr_smooth"]

        # ===== DX =====
        df["dx"] = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])

        # ===== ADX =====
        df["adx"] = df["dx"].ewm(alpha=1/period, adjust=False).mean()

        return df["adx"].tolist()
