import pandas as pd
import numpy as np
from operation import OperationModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
import time

# 设置储氢罐参数
h2_storage = solph.components.GenericStorage(
    nominal_storage_capacity=1760,  # 储气量
    label="air storage",
    inputs={air_bus: solph.Flow(nominal_value=1760)},
    outputs={air_bus: solph.Flow(nominal_value=1760)},
    loss_rate=0.03,  # 损耗率3%
    initial_storage_level=None,
    min_storage_level=1240 / 1760,  # 最小储气量
    inflow_conversion_factor=0.95,
    outflow_conversion_factor=0.95,

 def hydrogen_sold_rule(model):
     return (
         sum(model.flow[gas_bus, chp, t]
             for t in model.TIMESTEPS) <= 80000
     )
 model.hydrogen_sale_limit = po.Constraint(rule=hydrogen_sold_rule)