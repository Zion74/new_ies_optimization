import pandas as pd
import numpy as np
from operation import OperationModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
import time




chp = solph.Transformer(
    label='CHP',
    inputs={gas_bus: solph.Flow(nominal_value=250, min=15 / 250, max=1.0)},  # 输入流的最大值为250，最小值为15
    outputs={
        ele_bus: solph.Flow(nominal_value=250 * 3.3),  # 产电功率最大值
        heat_bus: solph.Flow(nominal_value=250 * 6.4)  # 产热功率最大值
    },
    conversion_factors={
        ele_bus: 3.3,  # 产电效率
        heat_bus: 6.4  # 产热效率
    }
)