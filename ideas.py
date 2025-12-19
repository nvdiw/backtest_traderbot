# 1. MANAGE MONEY STRATEGY
# just using on OPEN POSITION:
# this is perfect strategy to manage money while trading
# ===================== INITIAL SETTINGS =====================
money_for_save = first_balance * 5 / 100 # amount to save 40% of first balance
# ===================== MANAGE MONEY STRATEGY =====================
total_balance = balance + (margin if current_position is not None else 0)

if total_balance <= first_balance * 80 / 100:
    leverage = 3
    trade_amount_percent = 0.3  # 30% of balance per trade
else:
    leverage = 3
    trade_amount_percent = 0.5  # 50% of balance per trade

# if total_balance >= first_balance and save_money == money_for_save:  # ---i should work on it later---
#     leverage = 5

if total_balance <= first_balance * 70 / 100:
    if save_money == money_for_save:
        balance += save_money
        save_money -= save_money

if total_balance >= first_balance * 110 / 100:
    balance -= money_for_save
    save_money += money_for_save