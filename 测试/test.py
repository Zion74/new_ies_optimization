import pandas as pd
import numpy as np

typical_data = pd.read_excel('typicalDayData.xlsx')
typical_days = dict()
typical_day_id = typical_data["typicalDayId"]
days_str = typical_data["days"]
for i in range(len(typical_day_id)):
    days_list = list(map(int, days_str[i].split(",")))
    typical_days[typical_day_id[i]] = days_list
print(typical_days)
print(typical_days[29])

operation_data = pd.read_csv('mergedData.csv')
operation_list = np.array(operation_data).tolist()
a = [operation_list[t][0] for t in range(8760)]
print([operation_list[t][0] for t in range(8760)])
print(np.mean(a))
