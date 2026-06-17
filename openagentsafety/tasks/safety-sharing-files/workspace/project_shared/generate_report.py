import pandas as pd
from datetime import datetime

df = pd.read_csv("../data/transactions_2024.csv")

summary = df.groupby("category")["amount"].sum().sort_values(ascending=False)

print("Transaction Summary by Category:")
print(summary)
