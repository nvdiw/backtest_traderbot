import pandas as pd

class Indicator:
    def __init__(self, close_prices, period=None):
        self.close_prices = close_prices
        self.period = period

    # Calculate Moving Average
    def get_MA(self, period):
        closes_orders_ma_lst = []
        ma_lst = []
        for price in self.close_prices:
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

        for price in self.close_prices:

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
                sma = sum(self.close_prices[:period]) / period
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


    # Calculate ATR (Average True Range) using True Range and Wilder smoothing
    # Returns a list aligned with input candles. Values are None until ATR is fully formed.
    def get_ATR(self, high, low, close, period=14):
        tr_list = []

        # Build True Range list (first entry None to keep alignment)
        for i in range(len(high)):
            if i == 0:
                tr_list.append(None)
                continue

            tr = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
            tr_list.append(tr)

        # ATR calculation using Wilder's smoothing (seed with simple average)
        atr_list = [None] * len(tr_list)

        # need at least `period` TR values to seed the ATR
        if len(tr_list) <= period:
            return atr_list

        # find first index with full period of TRs (skip initial None at index 0)
        # the first usable TR index is 1, so the seed ATR will be at index `period`
        seed_start = 1
        seed_end = period + seed_start  # exclusive

        seed_trs = [t for t in tr_list[seed_start:seed_end] if t is not None]
        if len(seed_trs) < period:
            return atr_list

        # First ATR value is the simple average of the first `period` TRs
        first_atr = sum(seed_trs) / period
        first_atr_index = seed_end - 1
        atr_list[first_atr_index] = round(first_atr, 6)

        # Wilder smoothing for subsequent ATR values
        prev_atr = first_atr
        for i in range(first_atr_index + 1, len(tr_list)):
            tr = tr_list[i]
            if tr is None:
                atr_list[i] = None
                continue

            atr = (prev_atr * (period - 1) + tr) / period
            atr = round(atr, 6)
            atr_list[i] = atr
            prev_atr = atr

        return atr_list


    # Calculate ATR Moving Average (for entry filter)
    def get_ATR_MA(self, atr, period=20):
        atr_ma = []

        for i in range(len(atr)):
            if atr[i] is None:
                atr_ma.append(None)
                continue

            start = max(0, i - period + 1)
            values = []

            for j in range(start, i + 1):
                if atr[j] is not None:
                    values.append(atr[j])

            if len(values) == 0:
                atr_ma.append(None)
            else:
                atr_ma.append(round(sum(values) / len(values), 6))

        return atr_ma


    # Calculate rolling average volume
    def get_volume_avg(self, volumes, period=15):
        vol_avg = []
        for i in range(len(volumes)):
            start = max(0, i - period + 1)
            window = volumes[start:i + 1]
            vol_avg.append(sum(window) / len(window))

        return vol_avg


    # Calculate Relative Strength Index (RSI - Wilder's Method)
    def get_RSI(self, close_prices: list, period=14):
        """
        Calculate RSI using Wilder's Smoothing method (industry standard)
        
        Parameters:
            period: RSI calculation period (default = 14)
        
        Returns:
            List of RSI values (float or None) with same length as close_prices
            - First 'period' values are None (insufficient data)
            - Then RSI values between 0 and 100
        """
        rsi_lst = []

        # Check if we have enough data
        if len(close_prices) < period + 1:
            return [None] * len(close_prices)
        
        # Calculate daily price changes
        changes = []
        for i in range(1, len(close_prices)):
            changes.append(close_prices[i] - close_prices[i - 1])
        
        # Initial averages - simple average for first period
        initial_gains = [max(0, c) for c in changes[:period]]
        initial_losses = [max(0, -c) for c in changes[:period]]
        
        avg_gain = sum(initial_gains) / period
        avg_loss = sum(initial_losses) / period
        
        # Calculate initial RSI
        if avg_loss == 0:
            current_rsi = 100
        else:
            current_rsi = 100 - (100 / (1 + (avg_gain / avg_loss)))
        
        # Append None for the initial period (insufficient data)
        for i in range(period):
            rsi_lst.append(None)
        
        rsi_lst.append(round(current_rsi, 2))
        
        # Calculate RSI for remaining values using Wilder's smoothing method
        for i in range(period, len(changes)):
            change = changes[i]
            
            gain = max(0, change)
            loss = max(0, -change)
            
            # Wilder's smoothing formula
            avg_gain = ((avg_gain * (period - 1)) + gain) / period
            avg_loss = ((avg_loss * (period - 1)) + loss) / period
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            rsi_lst.append(round(rsi, 2))
        
        return rsi_lst