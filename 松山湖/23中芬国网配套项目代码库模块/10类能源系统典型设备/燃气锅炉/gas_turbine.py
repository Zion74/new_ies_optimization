      
  def __init__(self, local_time, time_step, ele_price, gas_price,
                 ele_load, heat_demand, cool_demand, wt_output, pv_output,
                 gt_capacity, ehp_capacity, ec_capacity, ac_capacity,
                 ele_storage_io, heat_storage_io, cool_storage_io):
        # 初始化能源系统模型
        logging.info("Initialize the energy system")
        self.date_time_index = pd.date_range(local_time, periods=time_step, freq="H")
        self.energy_system = solph.EnergySystem(timeindex=self.date_time_index)
        ##########################################################################
        # 创建能源系统设备对象
        ##########################################################################
        logging.info("Create oemof objects")
        # 创建电母线
        ele_bus = solph.Bus(label="electricity bus")
        # 创建热母线
        heat_bus = solph.Bus(label="heat bus")
        # 创建冷母线
        cool_bus = solph.Bus(label="cool bus")
        # 创建气母线
        gas_bus = solph.Bus(label="gas bus")
        # 将母线添加到模型中
        self.energy_system.add(ele_bus, heat_bus, cool_bus, gas_bus)
        # 添加电负荷
        self.energy_system.add(
            solph.Sink(
                label="electricity demand",
                inputs={ele_bus: solph.Flow(fix=ele_load, nominal_value=1)},
            )
        )
        # 添加热负荷
        self.energy_system.add(
            solph.Sink(
                label="heat demand",
                inputs={heat_bus: solph.Flow(fix=heat_demand, nominal_value=1)},
            )
        )
        # 添加冷负荷
        self.energy_system.add(
            solph.Sink(
                label="cool demand",
                inputs={cool_bus: solph.Flow(fix=cool_demand, nominal_value=1)},
            )
        )



  # 设置燃气轮机参数
        gt = solph.Transformer(
            label='gas turbine',
            inputs={gas_bus: solph.Flow()},
            outputs={ele_bus: solph.Flow(nominal_value=gt_capacity),
                     heat_bus: solph.Flow(nominal_value=gt_capacity*1.5)},
            conversion_factors={ele_bus: 0.33, heat_bus: 0.5}
        )
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
