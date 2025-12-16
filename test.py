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



# def trade_duration(open_time: str, close_time: str):
#     # format: YYYY-MM-DD HH:MM:SS.microseconds

#     def parse(t):
#         date, time = t.split(" ")
#         y, m, d = map(int, date.split("-"))
#         h, mi, s = time.split(":")
#         s = int(float(s))  # drop microseconds
#         return y, m, d, int(h), int(mi), s

#     def to_seconds(y, m, d, h, mi, s):
#         # days per month (no leap year handling for simplicity)
#         mdays = [31,28,31,30,31,30,31,31,30,31,30,31]

#         days = y * 365 + sum(mdays[:m-1]) + (d - 1)
#         return days * 86400 + h * 3600 + mi * 60 + s

#     o = to_seconds(*parse(open_time))
#     c = to_seconds(*parse(close_time))

#     diff = c - o

#     days = diff // 86400
#     diff %= 86400
#     hours = diff // 3600
#     diff %= 3600
#     minutes = diff // 60

#     return days, hours, minutes


# # example
# # trade_duration(
# #     "2025-12-06 13:00:00.000000",
# #     "2025-12-06 19:44:59.999000"
# # )

# days, hours, minutes = trade_duration(open_time ="2025-12-06 13:00:00.000000", close_time="2025-12-06 19:44:59.999000")
# print(f"Trade Duration: {days} days, {hours} hours, {minutes} minutes")




# High = 91000
# Low = 89000
# Close_previous = 90500
# ATR = max(
# High - Low,
# abs(High - Close_previous),
# abs(Low - Close_previous)
# )


# X = ATR / Close_previous
# print(f"True Range (TR): {ATR}")
# print(f"ATR as a percentage of Close_previous: {X*100:.2f}%")





# import pandas as pd

# df = pd.DataFrame({
#     "name": ["Navid", "Nila"],
#     "age": [25, 18],
#     "city": ["Tehran", "Tehran"]
# })

# df.to_csv("data.csv", index=False, encoding="utf-8")

# dfs = pd.DataFrame(["ali", 30, "Shiraz"], index=["name", "age", "city"])

# dfs.to_csv("data.csv", index=False, mode='a', header=False, encoding="utf-8")



# lst = [1, 2, 3, 4, 5]
# # print(lst[:3])
# print(min(lst))
# print(min(10, -5, 3))



class Car:
    def __init__(self, color):
        self.color = color
        self.speed = 0

    def accelerate(self):
        self.speed += 10

    def brake(self):
        self.speed -= 5

my_car = Car("red")
print(my_car.speed)
my_car.accelerate()
print(my_car.speed)
print(my_car.color)

print("-" * 20)

class person:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def birthday(self):
        self.age += 1

    def say_hello(self):
        print(f"Hello, my name is {self.name} and I am {self.age} years old.")

p = person("Navid", 20)
p.say_hello()
p.birthday()
p.say_hello()


print("-" * 20)

class counter:
    def __init__(self):
        self.count = 0

    def increace(self):
        self.count += 1

    def decrease(self):
        self.count -= 1

    def get_count(self):
        return self.count

count = counter()
print(count.get_count())
count.increace()
print(count.get_count())
count.decrease()
print(count.get_count())
for i in range(5):
    count.increace()

print(count.get_count())


print("-" * 20)

balance = 1000

def add_money(balance, amount):
    balance += amount
    return balance

print(balance)
print(add_money(balance, 500))
print(balance) # not added


print("-" * 20)

balance = 1000

class BankAccount:
    def __init__(self, initial_balance):
        self.balance = initial_balance

    def withdraw(self, amount):
        if amount <= self.balance:
            self.balance -= amount
        else:
            print("Not enough balance")

    def deposit(self, amount):
        self.balance += amount

    def get_balance(self):
        return self.balance
    

acc = BankAccount(balance)
acc.withdraw(1200)
acc.deposit(500)
print(acc.get_balance())   # 1500
acc.withdraw(200)
print(acc.get_balance())   # 1300

print(balance)  # 1000, original balance unchanged
