#   调用水力水力计算、热力计算和直流电力系统计算程序，完成考虑管道动态特性和不考虑动态特性工况的计算【2024-04-29】

import numpy as np
from openpyxl import load_workbook
import IHES_ReadNetworkPara_V2
import Hydraulic_Calculation
import Thermol_Calculation_For_different_heat_load_and_pipe_model
import Direct_Flow_Calculation_V3


# #######  进行多时段的水力工况计算
# Network = IHES_ReadNetworkPara_V2.ReadPara('6节点电力系统-14节点热力系统NEW-拓扑数据.xlsx', '6节点电力系统-14节点热力系统NEW-时序数据-用于水力计算.xlsx')
# for i in range(Network['VarPump'].shape[0]):
#     for t in range(24):
#         Network['TS_VarPumpFre'][i, t + 2] = 50
# Result = Hydraulic_Calculation.Hydraulic_Calculation(Network, '6节点电力系统14节点热力系统NEW-水力计算结果.xlsx', 24)


###### 进行多时段的热力模型计算
# ## 热力管道采用动态模型进行计算
# Network = IHES_ReadNetworkPara_V2.ReadPara('6节点电力系统-14节点热力系统NEW-拓扑数据.xlsx',
#                                            '6节点电力系统-14节点热力系统NEW-时序数据-热力计算输入数据.xlsx')
# Result = Thermol_Calculation_For_different_heat_load_and_pipe_model.CalThermolModel(Network, 24, '6节点电力系统-14节点热力系统NEW-时序数据-热力计算结果-动态管道模型.xlsx')
#
#
# ## 热力管道采用稳态模型进行计算
# Network = IHES_ReadNetworkPara_V2.ReadPara('6节点电力系统-14节点热力系统NEW-拓扑数据.xlsx',
#                                            '6节点电力系统-14节点热力系统NEW-时序数据-热力计算输入数据.xlsx')
# for i in range(Network['HeatPipe'].shape[0]):
#     Network['HeatPipe'][i, 13] = 2
# Result = Thermol_Calculation_For_different_heat_load_and_pipe_model.CalThermolModel(Network, 24, '6节点电力系统-14节点热力系统NEW-时序数据-热力计算结果-稳态管道模型.xlsx')

#
#######  进行多时段的电力系统直流潮流计算
## 基于管道采用【动态】模型所得CHP功率，进行多时段电力系统计算
CaseData = IHES_ReadNetworkPara_V2.ReadPara('6节点电力系统-14节点热力系统NEW-拓扑数据.xlsx',
                                           '6节点电力系统-14节点热力系统NEW-时序数据-直流电力模型计算输入数据-动态管道模型所得CHP电功率.xlsx')
Direct_Flow_Calculation_V3.DirectFlowMultiTime(CaseData, 24, '6节点电力系统-14节点热力系统NEW-时序数据-直流电力模型计算结果-动态管道模型所得CHP电功率.xlsx')

## 基于管道采用【稳态】模型所得CHP功率，进行多时段电力系统计算
CaseData = IHES_ReadNetworkPara_V2.ReadPara('6节点电力系统-14节点热力系统NEW-拓扑数据.xlsx',
                                           '6节点电力系统-14节点热力系统NEW-时序数据-直流电力模型计算输入数据-稳态管道模型所得CHP电功率.xlsx')
Direct_Flow_Calculation_V3.DirectFlowMultiTime(CaseData, 24, '6节点电力系统-14节点热力系统NEW-时序数据-直流电力模型计算结果-稳态管道模型所得CHP电功率.xlsx')
