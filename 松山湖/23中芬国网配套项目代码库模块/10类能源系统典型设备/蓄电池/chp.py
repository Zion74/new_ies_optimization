import pandas as pd
import numpy as np
from operation import OperationModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
import time



ele_storage = solph.components.GenericStorage(
    nominal_storage_capacity=864,  # 储电量
    label="electricity storage",
    inputs={ele_bus: solph.Flow(nominal_value=170)},
    outputs={ele_bus: solph.Flow(nominal_value=170)},
    loss_rate=0.01,
    initial_storage_level=None,
    min_storage_level=96 / 864,  # 最小储电量
    inflow_conversion_factor=0.95,
    outflow_conversion_factor=0.95
)