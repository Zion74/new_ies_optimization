import pandas as pd
import numpy as np
from operation import OperationModel
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool
import time

def cal_solar_output(solar_radiation_list, temperature_list, ppv):
    return [ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25)) for r, t in zip(solar_radiation_list, temperature_list)]


def cal_wind_output(wind_speed_list, pwt):
    ret = [0 for _ in range(len(wind_speed_list))]
    for i in range(len(wind_speed_list)):
        w = wind_speed_list[i]
        if 2.5 <= w < 9:
            ret[i] = (w ** 3 - 2.5 ** 3) / (9 ** 3 - 2.5 ** 3) * pwt
        elif 9 <= w < 25:
            ret[i] = pwt
    return ret


def operation(param):
    plan = param[0]
    year = param[1]
    operation_list = param[2]
    plan_list = param[3]
    rate = 1.01**year
    print("[plan:%d] [year:%f] [rate:%f] [startTime:%s]"
          % (plan, year, rate, time.strftime("%H:%M:%S", time.localtime())))

    time_step = 8760
    ele_price = [0.0025 for _ in range(time_step)]
    gas_price = [0.0286 for _ in range(time_step)]
    ele_load = [0 for _ in range(time_step)]
    heat_load = [0 for _ in range(time_step)]
    cool_load = [0 for _ in range(time_step)]
    solar_radiation_list = [0 for _ in range(time_step)]
    wind_speed_list = [0 for _ in range(time_step)]
    temperature_list = [0 for _ in range(time_step)]

    ppv = plan_list[plan][0]  # 光伏额定功率
    pwt = plan_list[plan][1]  # 风电额定功率
    pgt = plan_list[plan][2]  # 燃气轮机额定功率
    php = plan_list[plan][3]  # 电热泵额定功率
    pec = plan_list[plan][4]  # 电制冷额定功率
    pac = plan_list[plan][5]  # 吸收式制冷额定功率
    pes = plan_list[plan][6]  # 电储能额定功率
    phs = plan_list[plan][7]  # 热储能额定功率
    pcs = plan_list[plan][8]  # 冷储能额定功率

    # 调度模型参数设置
    for t in range(time_step):
        ele_load[t] = operation_list[t][0] * rate
        heat_load[t] = operation_list[t][1] * rate
        cool_load[t] = operation_list[t][2] * rate
        solar_radiation_list[t] = operation_list[t][3]
        wind_speed_list[t] = operation_list[t][4]
        temperature_list[t] = operation_list[t][5]
    pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
    wt_output = cal_wind_output(wind_speed_list, pwt)

    # 调度模型初始化及优化
    operation_model = OperationModel('01/01/2019', time_step, ele_price, gas_price,
                                     ele_load, heat_load, cool_load, wt_output, pv_output,
                                     pgt, php, pec, pac, pes, phs, pcs)
    # 优化并获取结果
    operation_model.optimise()
    objective_value = operation_model.get_objective_value()
    print("[plan:%d] [year:%f] [rate:%f] [cost:%f] [endTime:%s]"
          % (plan, year, rate, objective_value, time.strftime("%H:%M:%S", time.localtime())))
    return [plan, year, objective_value]


# 设置蓄热罐参数
heat_storage = solph.components.GenericStorage(
    nominal_storage_capacity=heat_storage_io * 4 / 3,
    label="heat storage",
    inputs={heat_bus: solph.Flow(nominal_value=heat_storage_io)},
    outputs={heat_bus: solph.Flow(nominal_value=heat_storage_io)},
    loss_rate=0.001,
    initial_storage_level=None,
    inflow_conversion_factor=0.9,
    outflow_conversion_factor=0.9,
)
# 设置蓄冷罐参数
cool_storage = solph.components.GenericStorage(
    nominal_storage_capacity=cool_storage_io * 4 / 3,
    label="cool storage",
    inputs={cool_bus: solph.Flow(nominal_value=cool_storage_io)},
    outputs={cool_bus: solph.Flow(nominal_value=cool_storage_io)},
    loss_rate=0.001,
    initial_storage_level=None,
    inflow_conversion_factor=0.9,
    outflow_conversion_factor=0.9,
)
# 将以上设备添加到系统中
self.energy_system.add(wt, pv, gt, grid, ac, ehp, ec, gas,
                       heat_source, cool_source,
                       ele_overflow, heat_overflow, cool_overflow,
                       ele_storage, heat_storage, cool_storage)
# 初始化模型
model = solph.Model(self.energy_system)

big_number = 100000000
# 创建求解计算电网电功率最大值的子模型
max_ele_load_block = po.Block()
# 将子模型添加到主模型中
model.add_component("max_ele_load_block", max_ele_load_block)
# 设置变量
model.max_ele_load_block.max_load = po.Var(model.TIMESTEPS, domain=po.NonNegativeReals)
model.max_ele_load_block.max_load_upper_switch = po.Var(model.TIMESTEPS, within=po.Binary)


# 设置计算功率下限约束规则
def max_ele_load_lower(m, s, e, t):
    return model.max_ele_load_block.max_load[0] >= model.flow[s, e, t]


# 设置计算功率上限约束规则
def max_ele_load_upper(m, s, e, t):
    return model.max_ele_load_block.max_load[0] <= \
        model.flow[s, e, t] + big_number * (1 - model.max_ele_load_block.max_load_upper_switch[t])


# 添加求解计算功率最大值的约束
model.max_ele_load_block.max_load_lower_constr = po.Constraint(
    [(grid, ele_bus)], model.TIMESTEPS, rule=max_ele_load_lower)
model.max_ele_load_block.max_load_upper_constr = po.Constraint(
    [(grid, ele_bus)], model.TIMESTEPS, rule=max_ele_load_upper)
model.max_ele_load_block.max_load_upper_switch_constr = po.Constraint(
    rule=(sum(model.max_ele_load_block.max_load_upper_switch[t] for t in model.TIMESTEPS) >= 1))

# 创建求解计算额外热源最大值的子模型
max_extra_heat_block = po.Block()
# 将子模型添加到主模型中
model.add_component("max_extra_heat_block", max_extra_heat_block)
# 设置变量
model.max_extra_heat_block.max_load = po.Var(model.TIMESTEPS, domain=po.NonNegativeReals)
model.max_extra_heat_block.max_load_upper_switch = po.Var(model.TIMESTEPS, within=po.Binary)


# 设置计算功率下限约束规则
def max_extra_heat_lower(m, s, e, t):
    return model.max_extra_heat_block.max_load[0] >= model.flow[s, e, t]


# 设置计算功率上限约束规则
def max_extra_heat_upper(m, s, e, t):
    return model.max_extra_heat_block.max_load[0] <= \
        model.flow[s, e, t] + big_number * (1 - model.max_extra_heat_block.max_load_upper_switch[t])


# 添加求解计算功率最大值的约束
model.max_extra_heat_block.max_load_lower_constr = po.Constraint(
    [(heat_source, heat_bus)], model.TIMESTEPS, rule=max_extra_heat_lower)
model.max_extra_heat_block.max_load_upper_constr = po.Constraint(
    [(heat_source, heat_bus)], model.TIMESTEPS, rule=max_extra_heat_upper)
model.max_extra_heat_block.max_load_upper_switch_constr = po.Constraint(
    rule=(sum(model.max_extra_heat_block.max_load_upper_switch[t] for t in model.TIMESTEPS) >= 1))

# 创建求解计算额外冷源最大值的子模型
max_extra_cool_block = po.Block()
# 将子模型添加到主模型中
model.add_component("max_extra_cool_block", max_extra_cool_block)
# 设置变量
model.max_extra_cool_block.max_load = po.Var(model.TIMESTEPS, domain=po.NonNegativeReals)
model.max_extra_cool_block.max_load_upper_switch = po.Var(model.TIMESTEPS, within=po.Binary)


# 设置计算功率下限约束规则
def max_extra_cool_lower(m, s, e, t):
    return model.max_extra_cool_block.max_load[0] >= model.flow[s, e, t]


# 设置计算功率上限约束规则
def max_extra_cool_upper(m, s, e, t):
    return model.max_extra_cool_block.max_load[0] <= \
        model.flow[s, e, t] + big_number * (1 - model.max_extra_cool_block.max_load_upper_switch[t])


# 添加求解计算功率最大值的约束
model.max_extra_cool_block.max_load_lower_constr = po.Constraint(
    [(cool_source, cool_bus)], model.TIMESTEPS, rule=max_extra_cool_lower)
model.max_extra_cool_block.max_load_upper_constr = po.Constraint(
    [(cool_source, cool_bus)], model.TIMESTEPS, rule=max_extra_cool_upper)
model.max_extra_cool_block.max_load_upper_switch_constr = po.Constraint(
    rule=(sum(model.max_extra_cool_block.max_load_upper_switch[t] for t in model.TIMESTEPS) >= 1))

# 定义考虑容量费和额外增加热/冷源成本的目标函数
objective_expr = 0
for t in model.TIMESTEPS:
    objective_expr += (model.flows[gas, gas_bus].variable_costs[t] * model.flow[gas, gas_bus, t]
                       + model.flows[grid, ele_bus].variable_costs[t] * model.flow[grid, ele_bus, t])
objective_expr += 114.29 * model.max_ele_load_block.max_load[0] \
                  + 102.53 * model.max_extra_heat_block.max_load[0] \
                  + 110.45 * model.max_extra_cool_block.max_load[0]
model.del_component('objective')
model.objective = po.Objective(expr=objective_expr)
self.model = model