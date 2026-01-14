# NOTE: Strategy executes ONLY on candle Open prices

import pandas as pd

# My Codes :
from trade_csv_logger import TradeCSVLogger
from indicators import Indicator
from get_candle_index import get_candle_index, get_month_start_indices
from trademanager import TradeManager
from check_monthly_data import write_monthly_summary


# start = get_candle_index("2025-01-01")   ----> 244944
# end = get_candle_index("2025-12-18")     ----> 278640

# get (index or ID) of start, end of csv
start, end = get_candle_index(("2025-01-01","2025-12-18"))
lst_month_starts = get_month_start_indices(start, end, just_index= True)

current_position = None  # None | "long" | "short"

# Fetch data from CSV file
def fetch_all_data(start : int, end : int):

    if start is None or end is None:
        return None
    
    df = pd.read_csv('./data_candle/btc_15m_data_2018_to_2025.csv')
    data = df.iloc[start:end]

    open_times_lst = []
    close_times_lst = []
    closes_prices_lst = []
    opens_prices_lst = []
    low_prices_lst = []
    high_prices_lst = []
    volume_prices_lst = []

    for index, row in data.iterrows():
        open_times_lst.append(row['Open time'])
        close_times_lst.append(row['Close time'])
        opens_prices_lst.append(row['Open'])
        closes_prices_lst.append(row['Close'])
        low_prices_lst.append(row['Low'])
        high_prices_lst.append(row['High'])
        volume_prices_lst.append(row['Volume'])

    return {
            "Open time": open_times_lst, 
            "Close time": close_times_lst,
            "Open": opens_prices_lst,
            "Close": closes_prices_lst,
            "Low": low_prices_lst,
            "High": high_prices_lst,
            "Volume" : volume_prices_lst
            }

all_data = fetch_all_data(start, end)
open_prices = all_data["Open"]
close_prices = all_data["Close"]
open_times = all_data["Open time"]
close_times = all_data["Close time"]
low_prices = all_data["Low"]
high_prices = all_data["High"]
volume_prices = all_data["Volume"]


# get average volume
def get_avg_volume(i, window=20):
    if i < window:
        return sum(volume_prices[:i+1]) / (i+1)
    else:
        return sum(volume_prices[i-window+1:i+1]) / window


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


# Main Trading Logic
def ma_strategy(tune: dict = None):

    global current_position

    csv_logger = TradeCSVLogger()

    # ---- settings is here ----
    balance = 1000     # base balance
    leverage = 10      # leverage
    safe_leverage = 3      # leverage safe mode
    trade_amount_percent = 0.5  # 50% of balance per trade
    monthly_profit_percent_stop_trade = 8    # if 8% per month profit --> don't trade on that month 
    monthly_compound = 3    # after get 'monthly_profit_percent_stop_trade' per month how much money goes for next month
    monthly_close_filter = True
    adx_filter = True
    volume_filter = True

    cooldown_after_big_pnl = 4 * 46  # 4 * 48  # 4 * x   [x] ---> number of candles per hour
    cooldown_until_index = -1

    ma_distance_threshold = 0.00204  # 0.2٪
    candle_move_threshold = 0.0082 # 0.8٪

    # Entry/exit tuning (avoid magic numbers; tweakable)
    slope_window = 3                # candles for EMA slope check
    entry_score_threshold = 6       # points required to trigger entry
    exit_score_threshold = 3        # points required to trigger exit
    atr_drawdown_mult = 1.5         # adverse move measured in ATR multiples
    atr_time_multiplier = 2         # scales allowable time in trade based on ATR
    atr_time_min = 1                # minimum candles before time-based exit contributes
    baseline_time_pct = 0.02        # reference price % used to compute dynamic time window

    # Apply tune overrides (explicit assignments to avoid relying on locals())
    if tune:
        if 'slope_window' in tune:
            slope_window = int(tune['slope_window'])

        if 'exit_score_threshold' in tune:
            exit_score_threshold = int(tune['exit_score_threshold'])

        if 'atr_drawdown_mult' in tune:
            atr_drawdown_mult = float(tune['atr_drawdown_mult'])

        if 'atr_time_multiplier' in tune:
            atr_time_multiplier = int(tune['atr_time_multiplier'])

        if 'atr_time_min' in tune:
            atr_time_min = int(tune['atr_time_min'])

        if 'baseline_time_pct' in tune:
            baseline_time_pct = float(tune['baseline_time_pct'])

        if 'trade_amount_percent' in tune:
            trade_amount_percent = float(tune['trade_amount_percent'])

        if 'monthly_profit_percent_stop_trade' in tune:
            monthly_profit_percent_stop_trade = int(tune['monthly_profit_percent_stop_trade'])

        if 'monthly_close_filter' in tune:
            monthly_close_filter = bool(tune['monthly_close_filter'])

        if 'adx_filter' in tune:
            adx_filter = bool(tune['adx_filter'])

        if 'volume_filter' in tune:
            volume_filter = bool(tune['volume_filter'])

        if 'leverage' in tune:
            leverage = float(tune['leverage'])

        if 'safe_leverage' in tune:
            safe_leverage = float(tune['safe_leverage'])


    # ---- fee rate ----
    fee_rate = 0.0005  # 0.05% per trade (entry or exit)

    save_money = 0
    total_wins = 0
    total_wins_long = 0
    total_wins_short = 0
    total_losses = 0
    total_long = 0
    total_short = 0
    total_profit_percent = 0
    deducting_fee_total = 0
    count_closed_orders = 0
    profit_percent_per_month = 0
    lst_profit_percent_per_month = []

    max_drawdown = 0
    equity_curve = []
    profits_lst = []

    current_position = None
    entry_price = None
    position_size = None
    position_size_no_fee = None
    balance_before_trade = None
    balance_before_trade_no_fee = None
    open_time_value = None

    # ---- Cross & Exit state and parameters ----
    cross_seen = False               # whether EMA14/MA50 have crossed at least once
    last_cross_dir = None           # 'bull' or 'bear'
    last_cross_index = None
    last_trade_cross_index = None   # index of the cross used to open the last trade

    trade_power = True

    balance_without_fee = balance
    first_balance = balance
    tactical_balance = first_balance

    first_open_time = open_times[0]
    last_close_time = open_times[-1]

    indicator = Indicator(open_prices, period=None)
    ema_14 = indicator.get_EMA(14)
    ma_50 = indicator.get_MA(50)
    ma_130 = indicator.get_MA(130)
    ma_200 = indicator.get_MA(200)



    # ---- MANAGE TRADES ----
    trade_manager = TradeManager(csv_logger, first_balance, monthly_profit_percent_stop_trade, 
                                 tactical_balance, monthly_close_filter, monthly_compound, leverage, safe_leverage)

    # ---- get_ADX ----
    indicator = Indicator(open_prices)
    adx = indicator.get_ADX(
        high_prices,
        low_prices,
        close_prices,
        period=14
    )

    # ---- get_ATR ----
    atr = indicator.get_ATR(
        high_prices,
        low_prices,
        close_prices,
        period=14
    )

    #   # check data loaded correctly :
    # print(len(open_prices), "candles loaded.")
    # print("len(ema_14):", len(ema_14))
    # print("len(ma_50):", len(ma_50))
    # print("len adx:", len(adx))

    # ---- MAIN ----
    for i in range(len(open_prices)):
        # print(start+i)
        if ema_14[i] is None or ma_50[i] is None or ma_130[i] is None or ma_200[i] is None:
            continue

        # ----- Detect EMA14 / MA50 crosses (update cross state) -----
        if i > 0 and ema_14[i-1] is not None and ma_50[i-1] is not None:
            # bullish cross: EMA crosses above MA
            if ema_14[i-1] <= ma_50[i-1] and ema_14[i] > ma_50[i]:
                cross_seen = True
                last_cross_dir = 'bull'
                last_cross_index = i
            # bearish cross: EMA crosses below MA
            elif ema_14[i-1] >= ma_50[i-1] and ema_14[i] < ma_50[i]:
                cross_seen = True
                last_cross_dir = 'bear'
                last_cross_index = i
        
        if monthly_close_filter == True:
            if trade_power == False:
                if int(start+i) in lst_month_starts:
                    lst_profit_percent_per_month.append(profit_percent_per_month)
                    profit_percent_per_month = 0
                    trade_power = True 
                else:
                    continue

        if i < cooldown_until_index:
            continue
        
        # Calculate MA Distance
        ma_distance = abs(ema_14[i] - ma_50[i]) / ma_50[i]

        # Calculate Distance New Candle Move and Last Candle Move
        if i > 0:
            last_candle_move = abs(open_prices[i] - open_prices[i-1]) / open_prices[i-1]
        else:
            last_candle_move = 0

        total_balance = balance + (margin if current_position is not None else 0)

        # ===================== CHECK LIQUIDATION =====================
        if current_position == "long":
            liquid_price_long = entry_price * (1 - 1 / leverage)

            if low_prices[i] <= liquid_price_long:

                close_price = liquid_price_long
                close_time_value = open_times[i]

                profit = -margin
                profit_percent = -100
                pnl_percent = -100
                total_fee_liq = 0 

                balance = balance_before_trade - margin
                balance_without_fee = balance_before_trade_no_fee - margin_no_fee

                deducting_fee_total += total_fee_liq
                count_closed_orders += 1
                total_losses += 1
                total_long += 1

                equity_curve.append(balance)
                peak = max(equity_curve)
                drawdown = (balance - peak) / peak * 100
                max_drawdown = min(max_drawdown, drawdown)

                days, hours, minutes = trade_duration(open_time_value, close_time_value)

                print("🔴 LONG LIQUIDATED at price:", round(close_price, 2),
                    "| Time:", close_time_value)

                # -------- CSV LOG --------
                csv_logger.log_trade(
                    "LONG_LIQUIDATED",           # Trade type
                    open_time_value,             # Open Time
                    close_time_value,            # Close Time
                    entry_price,                 # Entry Price
                    close_price,                 # Close Price
                    round(balance_before_trade,2),  # Balance before trade
                    round(balance,2),            # Balance after trade
                    round(margin,2),             # Margin used
                    leverage,                    # Leverage
                    trade_amount_percent,        # Trade amount percent
                    round(profit,2),             # Profit in $
                    round(profit_percent,2),     # Profit %
                    round(pnl_percent,2),        # PnL %
                    round(total_fee_liq,4),      # Total Fee
                    days,
                    hours,
                    minutes,
                    save_money,
                    profit_percent_per_month
                )

                current_position = None
                continue

        # ===================== CHECK LIQUIDATION =====================
        if current_position == "short":
            liquid_price_short = entry_price * (1 + 1 / leverage)

            if high_prices[i] >= liquid_price_short:

                close_price = liquid_price_short
                close_time_value = open_times[i]

                profit = -margin
                profit_percent = -100
                pnl_percent = -100
                total_fee_liq = 0

                balance = balance_before_trade - margin
                balance_without_fee = balance_before_trade_no_fee - margin_no_fee

                deducting_fee_total += total_fee_liq
                count_closed_orders += 1
                total_losses += 1
                total_short += 1

                equity_curve.append(balance)
                peak = max(equity_curve)
                drawdown = (balance - peak) / peak * 100
                max_drawdown = min(max_drawdown, drawdown)

                days, hours, minutes = trade_duration(open_time_value, close_time_value)

                print("🔴 SHORT LIQUIDATED at price:", round(close_price, 2),
                    "| Time:", close_time_value)

                # -------- CSV LOG --------
                csv_logger.log_trade(
                    "SHORT_LIQUIDATED",          # Trade type
                    open_time_value,             # Open Time
                    close_time_value,            # Close Time
                    entry_price,                 # Entry Price
                    close_price,                 # Close Price
                    round(balance_before_trade,2),  # Balance before trade
                    round(balance,2),            # Balance after trade
                    round(margin,2),             # Margin used
                    leverage,                    # Leverage
                    trade_amount_percent,        # Trade amount percent
                    round(profit,2),             # Profit in $
                    round(profit_percent,2),     # Profit %
                    round(pnl_percent,2),        # PnL %
                    round(total_fee_liq,4),      # Total Fee
                    days,
                    hours,
                    minutes,
                    save_money,
                    profit_percent_per_month
                )

                current_position = None
                continue


        # ===================== OPEN LONG =====================
        # Require that EMA/MA50 have crossed and the last cross was bullish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:
                entry_score = 0

                # 1) if last_cross is bull
                if last_cross_dir == 'bull':
                    entry_score += 1
                # 2) EMA 14 > Ma 50
                if ema_14[i] > ma_50[i]:
                    entry_score += 1
                # 3) Ma 130 > Ma 200
                if ma_130[i] >= ma_200[i]:
                    entry_score += 1
                # 4) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += 1
                # 5) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] is None or adx[i] < 20.5:
                        continue
                    else:
                        entry_score += 1

                # 6) ===== Volume FILTER =====
                if volume_filter == True :

                    vol_now = volume_prices[i]
                    vol_avg15 = get_avg_volume(i, window=15)

                    # ---- Strong Candle ----
                    body = abs(close_prices[i] - open_prices[i])
                    range_ = high_prices[i] - low_prices[i]

                    strong_candle = range_ > 0 and body >= 0.6 * range_

                    # ---- Volume Condition ----
                    volume_pass = vol_now >= 1.2 * vol_avg15

                    if not (volume_pass and strong_candle):
                        continue
                    else:
                        entry_score += 1

                if entry_score >= entry_score_threshold:
                    # ----open long
                    updates = trade_manager.open_long(
                        i,
                        open_prices,
                        open_times,
                        balance,
                        balance_without_fee,
                        first_balance,
                        trade_amount_percent,
                        total_balance,
                        leverage)
                    

                    entry_price = updates['entry_price']
                    balance = updates['balance']
                    balance_without_fee = updates['balance_without_fee']
                    balance_before_trade = updates['balance_before_trade']
                    balance_before_trade_no_fee = updates['balance_before_trade_no_fee']
                    margin = updates['margin']
                    leverage = updates['leverage']
                    position_size = updates['position_size']
                    margin_no_fee = updates['margin_no_fee']
                    position_size_no_fee = updates['position_size_no_fee']
                    open_time_value = updates['open_time_value']
                    current_position = updates['current_position']
                    # record which cross enabled this trade and ATR at entry
                    last_trade_cross_index = last_cross_index
                    entry_index = i
                    atr_at_entry = atr[i] if i < len(atr) else None
                    updates = None


        # ===================== CLOSE LONG =====================
        if current_position == "long":
            # exit scoring system (points accumulate; mirrored for short)
            exit_score = 0

            # 1) EMA slope weakness (look back `slope_window` candles)
            if i - slope_window >= 0 and ema_14[i] < ema_14[i - slope_window]:
                exit_score += 1

            # 2) EMA crossing below MA50
            if ema_14[i] < ma_50[i]:
                exit_score += 1

            # 3) long-term trend weakening (MA130 < MA200)
            if ma_130[i] < ma_200[i]:
                exit_score += 1

            # 4) adverse price move measured in ATR multiples
            if 'entry_price' in locals() and atr_at_entry is not None and atr_at_entry > 0:
                adverse = entry_price - low_prices[i]
                if adverse >= atr_at_entry * atr_drawdown_mult:
                    exit_score += 1

            # 5) ATR-based dynamic time exit (larger ATR -> shorter required time)
            if 'entry_index' in locals() and atr[i] is not None and atr[i] > 0:
                time_in_trade = i - entry_index
                atr_pct = atr[i] / entry_price if entry_price else 0
                # threshold_time scales inversely to ATR percentage relative to price
                threshold_time = max(
                    atr_time_min,
                    int((atr_time_multiplier * (baseline_time_pct / (atr_pct + 1e-12))))
                )
                if time_in_trade >= threshold_time:
                    exit_score += 1

            if exit_score >= exit_score_threshold:
                # ----close long
                updates = trade_manager.close_long(
                    i,
                    open_prices,
                    open_times,
                    entry_price,
                    position_size,
                    position_size_no_fee,
                    fee_rate,
                    margin,
                    margin_no_fee,
                    balance,
                    balance_without_fee,
                    balance_before_trade,
                    balance_before_trade_no_fee,
                    deducting_fee_total,
                    profits_lst,
                    total_profit_percent,
                    count_closed_orders,
                    equity_curve,
                    max_drawdown,
                    total_wins,
                    total_wins_long,
                    total_losses,
                    total_long,
                    cooldown_after_big_pnl,
                    leverage,
                    cooldown_until_index,
                    open_time_value,
                    csv_logger,
                    trade_amount_percent,
                    profit_percent_per_month,
                    save_money,
                    trade_power)

                balance = updates['balance']
                balance_without_fee = updates['balance_without_fee']
                deducting_fee_total = updates['deducting_fee_total']
                profits_lst = updates['profits_lst']
                total_profit_percent = updates['total_profit_percent']
                count_closed_orders = updates['count_closed_orders']
                equity_curve = updates['equity_curve']
                max_drawdown = updates['max_drawdown']
                total_wins = updates['total_wins']
                total_wins_long = updates['total_wins_long']
                total_losses = updates['total_losses']
                total_long = updates['total_long']
                cooldown_until_index = updates['cooldown_until_index']
                current_position = updates['current_position']
                profit_percent_per_month = updates['profit_percent_per_month']
                save_money = updates['save_money']
                trade_power = updates['trade_power']
                updates = None


        # ===================== OPEN SHORT =====================
        # Require that EMA/MA50 have crossed and the last cross was bearish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:
                entry_score = 0

                # 1) if last_cross is bear
                if last_cross_dir == 'bear':
                    entry_score += 1
                # 2) EMA 14 < Ma 50
                if ema_14[i] <= ma_50[i]:
                    entry_score += 1
                # 3) Ma 130 < Ma 200
                if ma_130[i] < ma_200[i]:
                    entry_score += 1
                # 4) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += 1
                # 5) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] is None or adx[i] < 20.5:
                        continue
                    else:
                        entry_score += 1

                # 6) ===== Volume FILTER =====
                if volume_filter == True :

                    vol_now = volume_prices[i]
                    vol_avg15 = get_avg_volume(i, window=15)

                    # ---- Strong Candle ----
                    body = abs(close_prices[i] - open_prices[i])
                    range_ = high_prices[i] - low_prices[i]

                    strong_candle = range_ > 0 and body >= 0.6 * range_

                    # ---- Volume Condition ----
                    volume_pass = vol_now >= 1.2 * vol_avg15

                    if not (volume_pass and strong_candle):
                        continue
                    else:
                        entry_score += 1

                if entry_score >= entry_score_threshold:
                    # ----open short
                    updates = trade_manager.open_short(
                        i,
                        open_prices,
                        open_times,
                        balance,
                        balance_without_fee,
                        first_balance,
                        trade_amount_percent,
                        total_balance,
                        leverage)
                    

                    entry_price = updates['entry_price']
                    balance = updates['balance']
                    balance_without_fee = updates['balance_without_fee']
                    balance_before_trade = updates['balance_before_trade']
                    balance_before_trade_no_fee = updates['balance_before_trade_no_fee']
                    margin = updates['margin']
                    leverage = updates['leverage']
                    position_size = updates['position_size']
                    margin_no_fee = updates['margin_no_fee']
                    position_size_no_fee = updates['position_size_no_fee']
                    open_time_value = updates['open_time_value']
                    current_position = updates['current_position']
                    # record which cross enabled this trade and ATR at entry
                    last_trade_cross_index = last_cross_index
                    entry_index = i
                    atr_at_entry = atr[i] if i < len(atr) else None
                    updates = None


        # ===================== CLOSE SHORT =====================
        if current_position == "short":
            # exit scoring (mirrored logic)
            exit_score = 0

            # 1) EMA slope weakness for short (EMA trending up)
            if i - slope_window >= 0 and ema_14[i] > ema_14[i - slope_window]:
                exit_score += 1

            # 2) EMA crossing above MA50
            if ema_14[i] > ma_50[i]:
                exit_score += 1

            # 3) long-term trend weakening for short (MA130 >= MA200)
            if ma_130[i] >= ma_200[i]:
                exit_score += 1

            # 4) adverse price move for short measured in ATR multiples
            if 'entry_price' in locals() and atr_at_entry is not None and atr_at_entry > 0:
                adverse = high_prices[i] - entry_price
                if adverse >= atr_at_entry * atr_drawdown_mult:
                    exit_score += 1

            # 5) ATR-based dynamic time exit for short
            if 'entry_index' in locals() and atr[i] is not None and atr[i] > 0:
                time_in_trade = i - entry_index
                atr_pct = atr[i] / entry_price if entry_price else 0
                # threshold_time scales inversely to ATR percentage relative to price
                threshold_time = max(
                    atr_time_min,
                    int((atr_time_multiplier * (baseline_time_pct / (atr_pct + 1e-12))))
                )
                if time_in_trade >= threshold_time:
                    exit_score += 1

            if exit_score >= exit_score_threshold:
                # ----close short
                updates = trade_manager.close_short(
                    i,
                    open_prices,
                    open_times,
                    entry_price,
                    position_size,
                    position_size_no_fee,
                    fee_rate,
                    margin,
                    margin_no_fee,
                    balance,
                    balance_without_fee,
                    balance_before_trade,
                    balance_before_trade_no_fee,
                    deducting_fee_total,
                    profits_lst,
                    total_profit_percent,
                    count_closed_orders,
                    equity_curve,
                    max_drawdown,
                    total_wins,
                    total_wins_short,
                    total_losses,
                    total_short,
                    cooldown_after_big_pnl,
                    leverage,
                    cooldown_until_index,
                    open_time_value,
                    csv_logger,
                    trade_amount_percent,
                    profit_percent_per_month,
                    save_money,
                    trade_power
                    )
                
                balance = updates['balance']
                balance_without_fee = updates['balance_without_fee']
                deducting_fee_total = updates['deducting_fee_total']
                profits_lst = updates['profits_lst']
                total_profit_percent = updates['total_profit_percent']
                count_closed_orders = updates['count_closed_orders']
                equity_curve = updates['equity_curve']
                max_drawdown = updates['max_drawdown']
                total_wins = updates['total_wins']
                total_wins_short = updates['total_wins_short']
                total_losses = updates['total_losses']
                total_short = updates['total_short']
                cooldown_until_index = updates['cooldown_until_index']
                current_position = updates['current_position']
                profit_percent_per_month = updates['profit_percent_per_month']
                save_money = updates['save_money']
                trade_power = updates['trade_power']
                updates = None


    # ===================== BACKTEST SUMMARY =====================

    if current_position is not None:
        balance += margin  # return margin if position still open
        balance_without_fee += margin_no_fee # return margin if position still open

    balance += save_money

    # summary calculation
    t_profit_percent = balance * 100 / first_balance - 100
    days, hours, minutes = trade_duration(first_open_time, last_close_time)
    win_rate = (total_wins / (total_wins + total_losses)) * 100 if (total_wins + total_losses) > 0 else 0


    print("✅ BACKTEST FINISHED")
    print("Closed Trades:", count_closed_orders, "( Longs:", total_long, "| Shorts:", total_short, ")")
    print("Total Wins:", total_wins, "| Total Wins Long:", total_wins_long, "| Total Wins Short:", total_wins_short)
    print("Total Losses:", total_losses)
    print("Final Balance:", round(balance, 2), "$")
    print("Final Balance (No Fee):", round(balance_without_fee, 2), "$")
    print("Total Fees Paid:", round(deducting_fee_total, 2), "$")
    print("Fee Compounding Impact:",
          round(balance_without_fee - balance - deducting_fee_total, 2), "$")
    print("Maximum Drawdown:", round(max_drawdown, 2), "%")
    print(f"Total Duration : {days} days, {hours} hours, {minutes} minutes")
    print("Win Rate:", round(win_rate, 2), "%")
    print("Total Profit:", round(sum(profits_lst), 2), "$")
    print("Total Profit Percent:", round(t_profit_percent, 2), "%", "or", round(total_profit_percent, 2), "%")
    print("saved Money:", round(save_money,2), "$")
    print("count_profit_more_than_8%_monthly:", len(lst_profit_percent_per_month))

    csv_logger.save_csv(
    first_balance=first_balance,
    final_balance=balance,
    total_profit=sum(profits_lst),
    total_profit_percent=t_profit_percent,
    total_fee=deducting_fee_total,
    start_time=first_open_time,
    end_time=last_close_time,
    days=days,
    hours=hours,
    minutes=minutes
    )

    # generate monthly summary CSV silently (no terminal output)
    try:
        write_monthly_summary(in_file='data_orders.csv', out_file='monthly_data_orders.csv', quiet=True)
    except Exception:
        # avoid crashing the backtest if monthly summary fails
        pass

    # return summary metrics for programmatic use
    return {
        'final_balance': balance,
        'total_profit': round(sum(profits_lst), 6),
        'total_profit_percent': round(t_profit_percent, 6),
        'closed_trades': count_closed_orders,
        'wins': total_wins,
        'losses': total_losses,
        "profit_more_than_8%": len(lst_profit_percent_per_month)
    }


    # Run the trading logic when executed as a script
if __name__ == "__main__":
    ma_strategy()

# print(open_prices[0])
# print(open_times[0])
# print(open_times[1])
# print(start, end)
# print(lst_month_starts)
# print(get_candle_index("2025-03-01"))
# print(get_candle_index("2025-02-27"))