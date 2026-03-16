



# 设置电制冷机组参数
ec = solph.Transformer(
    label='electricity chiller',
    inputs={ele_bus: solph.Flow()},
    outputs={cool_bus: solph.Flow(nominal_value=198)},
    conversion_factors={cool_bus: 2.81}
)


heat_cool_storage_block = po.Block()
# 将子模型添加到主模型中
model.add_component("heat_cool_storage_block", heat_cool_storage_block)
# 设置蓄冷蓄热模式开关变量，1为蓄热模式，0为蓄冷模式
heat_cool_storage_block.heat_switch = po.Var(model.TIMESTEPS, within=po.Binary)
# 设置蓄热模式约束规则，注意这里要区分传入参数m和model，
# m是由pyomo库传入的，因此是最底层的Model类，没有oemof的属性，
# 因此这里要用model（在这里是全局变量，因此可以出现在函数中）
def _heat_storage_rule(m, s, t):
    return model.GenericStorageBlock.storage_content[s, t] \
           <= heat_storage.nominal_storage_capacity * model.heat_cool_storage_block.heat_switch[t]
# 设置蓄冷模式约束规则
def _cool_storage_rule(m, s, t):
    return model.GenericStorageBlock.storage_content[s, t] \
           <= cool_storage.nominal_storage_capacity * (1 - model.heat_cool_storage_block.heat_switch[t])

# 添加蓄热模式约束
heat_cool_storage_block.heat_constr = po.Constraint(
    [heat_storage], model.TIMESTEPS, rule=_heat_storage_rule
)

# 添加蓄冷模式约束
heat_cool_storage_block.cool_constr = po.Constraint(
    [cool_storage], model.TIMESTEPS, rule=_cool_storage_rule
)

'''多台设备 多工况设备'''
# 同理，电制冷和电制热用的也是同一套机组，也要添加相应的约束
# 设置6台机组，单台制热量为37kW，制冷量为33kW
# 创建子模型
ele_heat_cool_block = po.Block()
# 将子模型添加到主模型中
model.add_component("ele_heat_cool_block", ele_heat_cool_block)
# 设置制热模式开启的机组数量
ele_heat_cool_block.heat_num = po.Var(model.TIMESTEPS, within=po.Integers, bounds=(0, 6))

# 设置制热约束规则
def _ele_heat_rule(m,flow_out, flow_in,t):
        return model.flow[flow_out, flow_in, t] \
           <= 37 * model.ele_heat_cool_block.heat_num[t]

# 设置制冷约束规则
def _ele_cool_rule(m, flow_out, flow_in, t):
    return model.flow[flow_out, flow_in, t] \
           <= 33 * (6 - model.ele_heat_cool_block.heat_num[t])

# 添加制热模式约束
ele_heat_cool_block.heat_constr = po.Constraint(
    [(ehp, heat_bus)], model.TIMESTEPS, rule=_ele_heat_rule
)
# 添加制冷模式约束
ele_heat_cool_block.cool_constr = po.Constraint(
    [(ec, cool_bus)], model.TIMESTEPS, rule=_ele_cool_rule
)


