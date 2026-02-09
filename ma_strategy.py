# NOTE: Strategy executes With candle Open prices, High prices, Low prices, Close prices

import pandas as pd
import matplotlib.pyplot as plt
import csv
import numpy as np

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
def fetch_all_data(start: int, end: int):
    """Optimized version using pandas vector operations"""
    if start is None or end is None:
        return None
    
    df = pd.read_csv('./data_candle/btc_15m_data_2018_to_2025.csv')
    data = df.iloc[start:end].copy()
    
    # vectorized
    return {
        "Open time": data['Open time'].tolist(),
        "Close time": data['Close time'].tolist(),
        "Open": data['Open'].astype(float).to_numpy(),
        "Close": data['Close'].astype(float).to_numpy(),
        "Low": data['Low'].astype(float).to_numpy(),
        "High": data['High'].astype(float).to_numpy(),
        "Volume": data['Volume'].astype(float).to_numpy()
    }

all_data = fetch_all_data(start, end)
open_prices = all_data["Open"]
close_prices = all_data["Close"]
open_times = all_data["Open time"]
close_times = all_data["Close time"]
low_prices = all_data["Low"]
high_prices = all_data["High"]
volume_prices = all_data["Volume"]

# normalize close_times by adding 0.001 seconds (1 ms) to make rounding consistent
close_times = (
    pd.to_datetime(close_times, utc=True) + pd.Timedelta(milliseconds=1)
).strftime("%Y-%m-%d %H:%M:%S.%f").tolist()

# --- performance: ensure numeric arrays and precompute rolling means (O(n)) ---
open_prices = np.asarray(open_prices, dtype=float)
close_prices = np.asarray(close_prices, dtype=float)
low_prices = np.asarray(low_prices, dtype=float)
high_prices = np.asarray(high_prices, dtype=float)
volume_prices = np.asarray(volume_prices, dtype=float)


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

    # detect optimization mode early so we can disable I/O and heavy bookkeeping
    optimize = bool(tune.get('optimize')) if tune else False
    csv_logger = TradeCSVLogger(optimize=optimize)

    # ---- settings is here ----
    balance = 1000     # base balance
    leverage = 10      # leverage
    safe_leverage_high = 4      # leverage safe mode high
    safe_leverage_med = 3      # leverage safe mode medium
    safe_leverage_low = 2      # leverage safe mode low
    trade_amount_percent = 0.5  # 50% of balance per trade
    monthly_profit_percent_stop_trade = 8    # if 8% per month profit --> don't trade on that month 
    monthly_compound = 3    # after get 'monthly_profit_percent_stop_trade' per month how much money goes for next month
    monthly_close_filter = True
    adx_filter = True
    volume_filter = True
    atr_filter = True
    skip_logic = False
    
    cooldown_after_big_pnl = 4 * 3  # [4 * 26] [4 * 3]  is good  # number of skip candles
    cooldown_until_index = -1        # best of cooldown_after_big_pnl: 4*12 , 4*46

    ma_distance_threshold = 0.00159  # 0.16٪
    candle_move_threshold = 0.008 # 0.8٪
    candle5_threshold = 100

    # Entry/exit tuning (avoid magic numbers; tweakable)
    slope_window = 3                # candles for EMA slope check
    entry_score_threshold = 6       # points required to trigger entry
    exit_score_threshold = 4        # points required to trigger exit
    trail_activate_pct = 0.007      # arm trailing after +0.7% move from entry
    trail_retrace_pct = 0.003       # exit if price retraces 0.3% from peak
    adx_exit_threshold = 15.0       # trend strength fade threshold
    adx_exit_lookback = 1           # confirm ADX is falling vs N candles ago
    entry_atr_threshold = 1.2       # 1, 1.1, 1.2, 1.3 should be test
    opposite_atr_body_mult = 0.6    # strong opposite candle body vs ATR
    
    # Apply tune overrides (explicit assignments to avoid relying on locals())
    if tune:
        if 'slope_window' in tune:
            slope_window = int(tune['slope_window'])

        if 'entry_score_threshold' in tune:
            entry_score_threshold = int(tune['entry_score_threshold'])

        if 'exit_score_threshold' in tune:
            exit_score_threshold = int(tune['exit_score_threshold'])

        if 'entry_atr_threshold' in tune:
            entry_atr_threshold = float(tune['entry_atr_threshold'])

        if 'ma_distance_threshold' in tune:
            ma_distance_threshold = float(tune['ma_distance_threshold'])

        if 'candle_move_threshold' in tune:
            candle_move_threshold = float(tune['candle_move_threshold'])

        if 'trail_activate_pct' in tune:
            trail_activate_pct = float(tune['trail_activate_pct'])

        if 'trail_retrace_pct' in tune:
            trail_retrace_pct = float(tune['trail_retrace_pct'])

        if 'adx_exit_threshold' in tune:
            adx_exit_threshold = float(tune['adx_exit_threshold'])

        if 'adx_exit_lookback' in tune:
            adx_exit_lookback = int(tune['adx_exit_lookback'])

        if 'opposite_atr_body_mult' in tune:
            opposite_atr_body_mult = float(tune['opposite_atr_body_mult'])

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

        if 'skip_logic' in tune:
            skip_logic = bool(tune['skip_logic'])

        if 'leverage' in tune:
            leverage = float(tune['leverage'])

        if 'safe_leverage_low' in tune:
            safe_leverage_low = float(tune['safe_leverage_low'])

        if 'safe_leverage_med' in tune:
            safe_leverage_med = float(tune['safe_leverage_med'])

        if 'safe_leverage_high' in tune:
            safe_leverage_high = float(tune['safe_leverage_high'])
            
        if 'cooldown_after_big_pnl' in tune:
            cooldown_after_big_pnl = int(tune['cooldown_after_big_pnl'])
    # ---- setting end ----

    # ---- fee rate ----
    fee_rate = 0.0005  # 0.05% per trade (entry or exit)

    save_money = 0
    total_wins = 0
    total_liquids = 0
    total_wins_long = 0
    total_wins_short = 0
    total_losses = 0
    total_long = 0
    total_short = 0
    total_profit_percent = 0
    deducting_fee_total = 0
    count_closed_orders = 0
    profit_percent_per_month = 0
    consecutive_losses = 0
    skip_trades_left = 0
    max_drawdown = 0

    lst_profit_percent_per_month = []

    equity_curve = []
    profits_lst = []
    chart_data = [] if not optimize else None
    # price chart trade markers
    long_open_points = [] if not optimize else None
    long_close_points = [] if not optimize else None
    short_open_points = [] if not optimize else None
    short_close_points = [] if not optimize else None

    current_position = None
    entry_price = None
    entry_index = None
    highest_since_entry = None
    lowest_since_entry = None
    position_size = None
    position_size_no_fee = None
    balance_before_trade = None
    balance_before_trade_no_fee = None
    open_time_value = None
    atr_ratio = None

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
    last_close_time = close_times[-1]

    # ---- Get MA, EMA ----
    indicator = Indicator(close_prices, period=None)

    # # good
    # ema_14 = 14
    # ma_50 = 50
    # ma_130 = 110
    # ma_200 = 230

    # best
    ema_14 = 16
    ma_50 = 50
    ma_130 = 100
    ma_200 = 200
    

    # Optimize: MA, EMA
    if tune:
        if 'ema_14' in tune:
            ema_14 = int(tune['ema_14'])
        if 'ma_50' in tune:
            ma_50 = int(tune['ma_50'])
        if 'ma_130' in tune:
            ma_130 = int(tune['ma_130'])
        if 'ma_200' in tune:
            ma_200 = int(tune['ma_200'])

    ema_14 = indicator.get_EMA(ema_14)
    ma_50 = indicator.get_MA(ma_50)
    ma_130 = indicator.get_MA(ma_130)
    ma_200 = indicator.get_MA(ma_200)



    # ---- MANAGE TRADES ----
    trade_manager = TradeManager(csv_logger, first_balance, monthly_profit_percent_stop_trade, 
                                 tactical_balance, monthly_close_filter, monthly_compound, leverage, safe_leverage_low,
                                 safe_leverage_med, safe_leverage_high)

    # ---- get_ADX ----
    # reuse existing `indicator` instance (created above) to avoid re-initialization
    adx = indicator.get_ADX(
        high_prices,
        low_prices,
        close_prices,
        period=14
    )

    # ---- get_ATR ----
    atr = indicator.get_ATR(high_prices, low_prices, close_prices, period=14)
    # ---- get_ATR_MA ----
    atr_ma = indicator.get_ATR_MA(atr, period=20)
    # ---- get volume average ----
    vol_avg_15_list = [sum(volume_prices[max(0, i-14):i+1]) / min(i+1, 15) for i in range(len(volume_prices))]

    # ---- time filter mask (13:30 UTC close time) ----
    close_times_utc = pd.to_datetime(close_times, utc=True)
    time_1330_mask = (close_times_utc.hour == 13) & (close_times_utc.minute == 30)

    #   # check data loaded correctly :
    # print(len(open_prices), "candles loaded.")
    # print("len(ema_14):", len(ema_14))
    # print("len(ma_50):", len(ma_50))
    # print("len adx:", len(adx))

    # ---- MAIN ----
    for i in range(len(close_prices)):
        # print(start+i)

        if chart_data is not None:
            chart_data.append([i, balance + (margin if current_position is not None else 0) + save_money])

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
        
        # monthly filter if we got good profit in month, bot will stop on this month
        if monthly_close_filter == True:
            if trade_power == False:
                if int(start+i) in lst_month_starts:
                    lst_profit_percent_per_month.append(profit_percent_per_month)
                    profit_percent_per_month = 0
                    trade_power = True 
                else:
                    continue
        
        # cooldown after good profit
        if i < cooldown_until_index:
            continue
        
        # Calculate MA Distance
        ma_distance = abs(ema_14[i] - ma_50[i]) / ma_50[i]

        # Calculate Distance New Candle Move and Last Candle Move
        if i > 0:
            last_candle_move = abs(close_prices[i] - open_prices[i]) / open_prices[i]
        else:
            last_candle_move = 0

        # Calculate total balance (if we have order we have: margin + balance)
        margin_balance = balance + (margin if current_position is not None else 0)

        # ===================== CHECK LIQUIDATION =====================
        # --- check long
        if current_position == "long":
            liq_updates = trade_manager.check_liquidation_long(
                i,
                low_prices,
                close_times,
                entry_price,
                leverage,
                margin,
                margin_no_fee,
                balance_before_trade,
                balance_before_trade_no_fee,
                balance,
                balance_without_fee,
                deducting_fee_total,
                count_closed_orders,
                total_losses,
                total_long,
                equity_curve,
                save_money,
                max_drawdown,
                open_time_value,
                csv_logger,
                trade_amount_percent,
                profit_percent_per_month,
                total_liquids
            )

            if liq_updates['liquidated']:
                balance = liq_updates['balance']
                balance_without_fee = liq_updates['balance_without_fee']
                deducting_fee_total = liq_updates['deducting_fee_total']
                count_closed_orders = liq_updates['count_closed_orders']
                total_losses = liq_updates['total_losses']
                total_long = liq_updates['total_long']
                equity_curve = liq_updates['equity_curve']
                max_drawdown = liq_updates['max_drawdown']
                total_liquids = liq_updates['total_liquids']
                current_position = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if long_close_points is not None:
                    long_close_points.append((i, liq_updates['close_price']))
                continue
        
        # ---- check short
        if current_position == "short":
            liq_updates = trade_manager.check_liquidation_short(
                i,
                high_prices,
                close_times,
                entry_price,
                leverage,
                margin,
                margin_no_fee,
                balance_before_trade,
                balance_before_trade_no_fee,
                balance,
                balance_without_fee,
                deducting_fee_total,
                count_closed_orders,
                total_losses,
                total_short,
                equity_curve,
                save_money,
                max_drawdown,
                open_time_value,
                csv_logger,
                trade_amount_percent,
                profit_percent_per_month,
                total_liquids
            )

            if liq_updates['liquidated']:
                balance = liq_updates['balance']
                balance_without_fee = liq_updates['balance_without_fee']
                deducting_fee_total = liq_updates['deducting_fee_total']
                count_closed_orders = liq_updates['count_closed_orders']
                total_losses = liq_updates['total_losses']
                total_short = liq_updates['total_short']
                equity_curve = liq_updates['equity_curve']
                max_drawdown = liq_updates['max_drawdown']
                total_liquids = liq_updates['total_liquids']
                current_position = None
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if short_close_points is not None:
                    short_close_points.append((i, liq_updates['close_price']))
                continue


        # ===================== OPEN LONG =====================
        # Require that EMA/MA50 have crossed and the last cross was bullish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:

                entry_score = 0

                # ===== ATR ENTRY FILTER =====
                if atr_filter == True:
                    if atr[i] is None or atr_ma[i] is None:
                        continue

                    atr_ratio = atr[i] / atr_ma[i]

                    if atr_ratio < entry_atr_threshold:
                        continue

                # ---- positive scores
                # 1) CONFIRMED BULL CROSS
                if last_cross_dir == 'bull' and last_cross_index is not None:
                    # wait at least 1 candle after cross
                    if i > last_cross_index:
                        # price acceptance above EMA after cross
                        if close_prices[i] > ema_14[i]:
                            entry_score += 1
                # 2) EMA 14 > Ma 50
                if ema_14[i] > ma_50[i]:
                    entry_score += 1
                # 3) Ma 130 > Ma 200
                if ma_130[i] >= ma_200[i]:
                    entry_score += 1
                # 3.5) EMA14 > MA50 and MA100 > MA200 at 13:30 UTC
                if (ema_14[i] > ma_50[i]) and (ma_130[i] > ma_200[i]) and time_1330_mask[i]:
                    entry_score += 1
                # 4) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += 1
                # 5) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] != None and adx[i] >= 20.5:
                        entry_score += 1
                # 6) ===== VOLUME FILTER =====
                if volume_filter:
                    vol_now = volume_prices[i]
                    vol_avg15 = vol_avg_15_list[i]
                    if vol_now >= 1.25 * vol_avg15:
                        entry_score += 1
                # ---- negative scores
                # 1) Comparing: current candle (i) with candle 5 periods earlier (i-5)
                if ((close_prices[i] * 100 / close_prices[i-5]) - 100) > candle5_threshold:
                    entry_score -= 1

                if entry_score >= entry_score_threshold:
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
                        print(f"⏭️ SKIP LONG | skips left: {skip_trades_left}")
                        continue

                    # ---- open long ----
                    updates = trade_manager.open_long(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        first_balance,
                        trade_amount_percent,
                        margin_balance,
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
                    if long_open_points is not None:
                        long_open_points.append((i, entry_price))
                    # record which cross enabled this trade and init trailing state
                    last_trade_cross_index = last_cross_index
                    entry_index = i
                    highest_since_entry = max(entry_price, high_prices[i])
                    lowest_since_entry = min(entry_price, low_prices[i])

                    updates = None


        # ===================== CLOSE LONG =====================
        if current_position == "long":
            # exit scoring system (points accumulate; mirrored for short)
            exit_score = 0

            # update trailing peak
            if highest_since_entry is None:
                highest_since_entry = entry_price
            if high_prices[i] > highest_since_entry:
                highest_since_entry = high_prices[i]

            # 1) EMA slope weakness (look back `slope_window` candles)
            if i - slope_window >= 0 and ema_14[i] < ema_14[i - slope_window]:
                exit_score += 1

            # 2) EMA crossing below MA50
            if ema_14[i] < ma_50[i]:
                exit_score += 1

            # 3) long-term trend weakening (MA130 < MA200)
            if ma_130[i] < ma_200[i]:
                exit_score += 1

            # 4) trailing stop based on pullback from peak (armed after min profit)
            if entry_index is not None and i > entry_index:
                if highest_since_entry >= entry_price * (1 + trail_activate_pct):
                    if close_prices[i] <= highest_since_entry * (1 - trail_retrace_pct):
                        exit_score += 1

            # 5) ADX weakening (trend strength fading)
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += 1

            # 6) strong opposite candle (body >= ATR * mult)
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] < open_prices[i]:
                    body = open_prices[i] - close_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += 1

            if exit_score >= exit_score_threshold:
                # ---- close long ----
                close_price = close_prices[i]
                updates = trade_manager.close_long(
                    i,
                    close_prices,
                    close_times,
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
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if long_close_points is not None:
                    long_close_points.append((i, close_price))
                
                # count consecutive_losses 
                if profits_lst[-1] < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

                if consecutive_losses >= 2:
                    skip_trades_left = 2
                    consecutive_losses = 0

        # ===================== OPEN SHORT =====================
        # Require that EMA/MA50 have crossed and the last cross was bearish,
        # and avoid opening multiple trades for the same cross.
        if current_position is None:
            if cross_seen and last_trade_cross_index != last_cross_index:
                
                entry_score = 0
                
                # ===== ATR ENTRY FILTER =====
                if atr_filter == True:
                    if atr[i] is None or atr_ma[i] is None:
                        continue

                    atr_ratio = atr[i] / atr_ma[i]

                    if atr_ratio < entry_atr_threshold:
                        continue
                # ---- positive scores
                # # 1) CONFIRMED BEAR CROSS
                if last_cross_dir == 'bear' and last_cross_index is not None:
                    # wait at least 1 candle after cross
                    if i > last_cross_index:
                        # price acceptance below EMA after cross
                        if close_prices[i] < ema_14[i]:
                            entry_score += 1
                # 2) EMA 14 < Ma 50
                if ema_14[i] <= ma_50[i]:
                    entry_score += 1
                # 3) Ma 130 < Ma 200
                if ma_130[i] < ma_200[i]:
                    entry_score += 1
                # 3.5) EMA14 < MA50 and MA100 < MA200 at 13:30 UTC
                if (ema_14[i] < ma_50[i]) and (ma_130[i] < ma_200[i]) and time_1330_mask[i]:
                    entry_score += 1
                # 4) ma_distance or last_candle_move is strong
                if ma_distance > ma_distance_threshold or last_candle_move > candle_move_threshold:
                    entry_score += 1
                # 5) ===== ADX FILTER =====
                if adx_filter == True :
                    if adx[i] != None and adx[i] >= 20.5:
                        entry_score += 1
                # 6) ===== VOLUME FILTER =====
                if volume_filter:
                    vol_now = volume_prices[i]
                    vol_avg15 = vol_avg_15_list[i]
                    if vol_now >= 1.25 * vol_avg15:
                        entry_score += 1
                # ---- negative scores
                # 1) Comparing: current candle (i) with candle 5 periods earlier (i-5)
                if (100 - (close_prices[i] * 100 / close_prices[i-5])) > candle5_threshold:
                    entry_score -= 1


                if entry_score >= entry_score_threshold:
                    # ===== SKIP LOGIC =====
                    if skip_logic and skip_trades_left > 0:
                        skip_trades_left -= 1
                        last_trade_cross_index = last_cross_index
                        print(f"⏭️ SKIP SHORT | skips left: {skip_trades_left}")
                        continue

                    # ---- open short ----
                    updates = trade_manager.open_short(
                        i,
                        close_prices,
                        close_times,
                        balance,
                        balance_without_fee,
                        first_balance,
                        trade_amount_percent,
                        margin_balance,
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
                    if short_open_points is not None:
                        short_open_points.append((i, entry_price))
                    # record which cross enabled this trade and init trailing state
                    last_trade_cross_index = last_cross_index
                    entry_index = i
                    highest_since_entry = max(entry_price, high_prices[i])
                    lowest_since_entry = min(entry_price, low_prices[i])

                    updates = None


        # ===================== CLOSE SHORT =====================
        if current_position == "short":
            # exit scoring (mirrored logic)
            exit_score = 0

            # update trailing trough
            if lowest_since_entry is None:
                lowest_since_entry = entry_price
            if low_prices[i] < lowest_since_entry:
                lowest_since_entry = low_prices[i]

            # 1) EMA slope weakness for short (EMA trending up)
            if i - slope_window >= 0 and ema_14[i] > ema_14[i - slope_window]:
                exit_score += 1

            # 2) EMA crossing above MA50
            if ema_14[i] > ma_50[i]:
                exit_score += 1

            # 3) long-term trend weakening for short (MA130 >= MA200)
            if ma_130[i] >= ma_200[i]:
                exit_score += 1

            # 4) trailing stop based on pullback from trough (armed after min profit)
            if entry_index is not None and i > entry_index:
                if lowest_since_entry <= entry_price * (1 - trail_activate_pct):
                    if close_prices[i] >= lowest_since_entry * (1 + trail_retrace_pct):
                        exit_score += 1

            # 5) ADX weakening (trend strength fading)
            if i - adx_exit_lookback >= 0:
                adx_now = adx[i]
                adx_prev = adx[i - adx_exit_lookback]
                if adx_now is not None and adx_prev is not None:
                    if np.isfinite(adx_now) and np.isfinite(adx_prev):
                        if adx_now < adx_exit_threshold and adx_now < adx_prev:
                            exit_score += 1

            # 6) strong opposite candle (body >= ATR * mult)
            if atr[i] is not None and atr[i] > 0:
                if close_prices[i] > open_prices[i]:
                    body = close_prices[i] - open_prices[i]
                    if body >= atr[i] * opposite_atr_body_mult:
                        exit_score += 1

            if exit_score >= exit_score_threshold:
                # ---- close short ----
                close_price = close_prices[i]
                updates = trade_manager.close_short(
                    i,
                    close_prices,
                    close_times,
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
                entry_price = None
                entry_index = None
                highest_since_entry = None
                lowest_since_entry = None
                if short_close_points is not None:
                    short_close_points.append((i, close_price))
                
                # count consecutive_losses 
                if profits_lst[-1] < 0:
                    consecutive_losses += 1
                else:
                    consecutive_losses = 0

                if consecutive_losses >= 2:
                    skip_trades_left = 2
                    consecutive_losses = 0

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
    print("Count Liquids:", total_liquids)
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

    # optimize already determined earlier; skip plotting when optimizing
    # Draw diagram
    if optimize is False:
            #plot 1 balance:
            xpoints_candles = []
            ypoints_total_balance = []

            for i in chart_data:
                xpoints_candles.append(i[0])
                ypoints_total_balance.append(i[1])

            xpoints = np.array(xpoints_candles)
            ypoints = np.array(ypoints_total_balance)
            plt.subplot(2, 1, 1)
            plt.plot(xpoints, ypoints)
            plt.title("Equity Curve", loc = 'left')
            plt.xlabel("Candles")
            plt.ylabel("Balance ($)")

            #plot 2 symbol_price:
            xpoints = np.array(xpoints_candles)
            ypoints_price = np.array(close_prices)
            ypoints_ema14 = np.array(ema_14)
            ypoints_ma50 = np.array(ma_50)
            ypoints_ma130 = np.array(ma_130)
            ypoints_ma200 = np.array(ma_200)
            # mark 13:30 UTC close points (use close_times)
            close_times_utc = pd.to_datetime(close_times, utc=True)
            mark_mask = (close_times_utc.hour == 13) & (close_times_utc.minute == 30)
            mark_x = xpoints[mark_mask]
            mark_y = ypoints_price[mark_mask]

            plt.subplot(2, 1, 2)
            plt.plot(xpoints, ypoints_price)
            plt.plot(xpoints, ypoints_ema14, color = '#DD8AFF')
            plt.plot(xpoints, ypoints_ma50, color = "#70009D")
            plt.plot(xpoints, ypoints_ma130, color = "#FFF98C")
            plt.plot(xpoints, ypoints_ma200, color = "#A49C00")
            if len(mark_x) > 0:
                plt.scatter(mark_x, mark_y, color="#00D4FF", s=60, zorder=6, edgecolors="black", linewidths=0.6, marker="o")
            if long_open_points:
                lo_x, lo_y = zip(*long_open_points)
                plt.scatter(lo_x, lo_y, color="#8FD18F", s=55, zorder=7, edgecolors="black", linewidths=0.5, marker="s")
            if long_close_points:
                lc_x, lc_y = zip(*long_close_points)
                plt.scatter(lc_x, lc_y, color="#1B7F2A", s=55, zorder=7, edgecolors="black", linewidths=0.5, marker="D")
            if short_open_points:
                so_x, so_y = zip(*short_open_points)
                plt.scatter(so_x, so_y, color="#FF6060", s=55, zorder=7, edgecolors="black", linewidths=0.5, marker="s")
            if short_close_points:
                sc_x, sc_y = zip(*short_close_points)
                plt.scatter(sc_x, sc_y, color="#B00020", s=55, zorder=7, edgecolors="black", linewidths=0.5, marker="D")
            plt.title("BTC - PRICE", loc = 'left')
            plt.xlabel("Candles")
            plt.ylabel("Prise")
            plt.show()

    # generate monthly summary CSV silently (no terminal output)
    if not optimize:
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
        'maximum_drawdown': round(max_drawdown, 2),
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
