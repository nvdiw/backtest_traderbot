class Indicator:
    def __init__(self, open_prices, period):
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

