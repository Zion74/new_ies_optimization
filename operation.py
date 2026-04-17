"""
综合能源系统调度
-------------------
园区能源拓扑结构：
                  input/output  ele_bus  heat_bus  cool_bus  gas_bus
                        |          |         |         |         |
 wt(FixedSource)        |--------->|         |         |         |
                        |          |         |         |         |
 pv(FixedSource)        |--------->|         |         |         |
                        |          |         |         |         |
 gas(Commodity)         |--------------------------------------->|
                        |          |         |         |         |
 grid(Commodity)        |--------->|         |         |         |
                        |          |         |         |         |
 ele_demand(Sink)       |<---------|         |         |         |
                        |          |         |         |         |
 heat_demand(Sink)      |<-------------------|         |         |
                        |          |         |         |         |
 cool_demand(Sink)      |<-----------------------------|         |
                        |          |         |         |         |
                        |<---------------------------------------|
 gt(Transformer)        |--------->|         |         |         |
                        |------------------->|         |         |
                        |          |         |         |         |
                        |<---------|         |         |         |
 ac(Transformer)        |<-------------------|         |         |
                        |----------------------------->|         |
                        |          |         |         |         |
 ehp(Transformer)       |<---------|         |         |         |
                        |------------------->|         |         |
                        |          |         |         |         |
 ec(Transformer)        |<---------|         |         |         |
                        |----------------------------->|         |
                        |          |         |         |         |
 es(Storage)            |<---------|         |         |         |
                        |--------->|         |         |         |
                        |          |         |         |         |
 hs(Storage)            |<-------------------|         |         |
                        |------------------->|         |         |
                        |          |         |         |         |
 cs(Storage)            |<-----------------------------|         |
                        |----------------------------->|         |
                  input/output  ele_bus  heat_bus  cool_bus  gas_bus
符号说明：
wt - wind turbine
pv - photovoltaic
gas - natural gas
grid - grid electricity
ele_demand - electricity demand
heat_demand - heat demand
cool_demand - cool demand
gt - gas turbine
ehp - electricity heat pump
ac - absorption chiller
ec - electricity chiller
es - electricity storage
hs - heat storage
cs - cool storage
"""

import logging
import tempfile
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
import pprint as pp
import pyomo.environ as po
import oemof.solph as solph
from oemof.solph import Sink, Source, Transformer
from oemof.solph.components import GenericStorage
import matplotlib.pyplot as plt
from pyomo.opt import ProblemFormat, SolverStatus, TerminationCondition

from solver_config import (
    configure_gurobi_license,
    iter_solver_display_names,
    preferred_solver_order,
    solver_display_name,
)

# 忽略 oemof 的 FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning, module="oemof")
configure_gurobi_license()


def _check_pyomo_results(results, solver_name):
    """Accept optimal solves and keep error messages readable across solvers."""
    status = results.solver.status
    cond = results.solver.termination_condition
    if status == SolverStatus.ok and cond in (
        TerminationCondition.optimal,
        TerminationCondition.unknown,
    ):
        return
    if cond == TerminationCondition.infeasible:
        raise ValueError(f"{solver_name} returned Infeasible")
    raise ValueError(f"{solver_name} status: {status}, condition: {cond}")


def _verify_model_solution(model):
    """Guard against empty solution objects when a solver silently fails."""
    for var in model.component_data_objects(ctype=po.Var, active=True):
        if var.value is not None:
            return
    raise ValueError("Solver returned no variable values")


def _build_manual_meta(objective_value, backend_name, message):
    return {
        "objective": float(objective_value),
        "problem": {"name": "IES optimisation model"},
        "solver": {
            "status": "ok",
            "termination_condition": "optimal",
            "message": message,
            "backend": backend_name,
        },
    }


def _solve_with_pyomo_backend(model, solver_name, solver_verbose):
    backend_name = solver_display_name(solver_name)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=".*termination condition unknown.*"
        )
        results = model.solve(
            solver=solver_name, solve_kwargs={"tee": solver_verbose}
        )
    _check_pyomo_results(results, backend_name)
    _verify_model_solution(model)
    meta = solph.processing.meta_results(model)
    meta.setdefault("solver", {})
    meta["solver"]["backend"] = backend_name
    return model, meta


def _load_highs_solution(model, symbol_map, highs_model, highspy):
    solution = highs_model.getSolution()
    if not solution.value_valid:
        raise ValueError("HiGHS returned no primal solution")

    var_by_symbol = {}
    for symbol, obj_ref in symbol_map.bySymbol.items():
        obj = obj_ref()
        if obj is not None and getattr(obj, "is_variable_type", lambda: False)():
            var_by_symbol[symbol] = obj

    for col_index, value in enumerate(solution.col_value):
        col_status, col_name = highs_model.getColName(col_index)
        if col_status != highspy.HighsStatus.kOk:
            continue
        var = var_by_symbol.get(col_name)
        if var is not None:
            try:
                var.set_value(value, skip_validation=True)
            except TypeError:
                var.set_value(value)

    _verify_model_solution(model)


def _solve_with_highs_backend(model, solver_verbose):
    try:
        import highspy
    except ImportError as exc:
        raise ValueError(
            "highspy is not installed. Run `uv sync` after adding the dependency."
        ) from exc

    with tempfile.TemporaryDirectory(prefix="ies_highs_") as tmp_dir:
        lp_path = Path(tmp_dir) / "model.lp"
        _, symbol_map_id = model.write(
            str(lp_path),
            format=ProblemFormat.cpxlp,
            io_options={"symbolic_solver_labels": True},
        )
        symbol_map = model.solutions.symbol_map[symbol_map_id]

        highs_model = highspy.Highs()
        highs_model.setOptionValue("output_flag", bool(solver_verbose))

        read_status = highs_model.readModel(str(lp_path))
        if read_status != highspy.HighsStatus.kOk:
            raise ValueError(f"HiGHS could not read LP file: {read_status}")

        run_status = highs_model.run()
        if run_status != highspy.HighsStatus.kOk:
            raise ValueError(f"HiGHS run() failed: {run_status}")

        model_status = highs_model.getModelStatus()
        if model_status != highspy.HighsModelStatus.kOptimal:
            status_text = highs_model.modelStatusToString(model_status)
            raise ValueError(f"HiGHS status: {status_text}")

        _load_highs_solution(model, symbol_map, highs_model, highspy)
        status_text = highs_model.modelStatusToString(model_status)
        objective_value = highs_model.getObjectiveValue()

    model.es.results = {
        "Problem": [{"Name": "IES optimisation model"}],
        "Solver": [
            {
                "Status": "ok",
                "Termination condition": "optimal",
                "Message": status_text,
                "Name": "HiGHS",
            }
        ],
    }
    return model, _build_manual_meta(objective_value, "HiGHS", status_text)


def _solve_model_with_priority(instance, solver_verbose):
    solver_order = preferred_solver_order()
    last_errors = []
    model = instance.model
    meta = None
    solver_used = None

    for idx, solver_name in enumerate(solver_order):
        if idx > 0:
            model = solph.Model(instance.energy_system)

        try:
            if solver_name == "highs":
                model, meta = _solve_with_highs_backend(model, solver_verbose)
            else:
                model, meta = _solve_with_pyomo_backend(
                    model, solver_name, solver_verbose
                )
            solver_used = solver_name
            break
        except Exception as exc:
            last_errors.append(
                f"{solver_display_name(solver_name)} failed: {exc}"
            )

    if solver_used is None:
        raise ValueError(
            "All solver attempts failed "
            f"({iter_solver_display_names(solver_order)}): "
            + " | ".join(last_errors)
        )

    meta.setdefault("solver", {})
    meta["solver"]["backend"] = solver_display_name(solver_used)
    meta["solver"]["order"] = iter_solver_display_names(solver_order)

    instance.model = model
    instance.last_solver_used = solver_used
    instance.last_solver_order = list(solver_order)
    instance.energy_system.results["main"] = solph.processing.results(model)
    instance.energy_system.results["meta"] = meta


class OperationModel:
    # 初始化模型
    def __init__(
        self,
        local_time,
        time_step,
        ele_price,
        gas_price,
        ele_load,
        heat_demand,
        cool_demand,
        wt_output,
        pv_output,
        gt_capacity,
        ehp_capacity,
        ec_capacity,
        ac_capacity,
        ele_storage_io,
        heat_storage_io,
        cool_storage_io,
        config=None,        # 案例配置（None则使用默认值，向后兼容）
        cb_power=0,         # 卡诺电池功率 (kW)
        cb_capacity=0,      # 卡诺电池容量 (kWh)
    ):
        self.time_step = time_step
        # 从配置读取设备参数，若无配置则使用原始硬编码值
        cfg = config or {}
        gt_eta_e = cfg.get("gt_eta_e", 0.33)
        gt_eta_h = cfg.get("gt_eta_h", 0.50)
        ac_cop = cfg.get("ac_cop", 0.75)
        ac_heat_ratio = cfg.get("ac_heat_ratio", 0.983)
        ac_ele_ratio = cfg.get("ac_ele_ratio", 0.017)
        ehp_cop = cfg.get("ehp_cop", 4.44)
        ec_cop = cfg.get("ec_cop", 2.87)
        es_charge_eff = cfg.get("es_charge_eff", 0.95)
        es_discharge_eff = cfg.get("es_discharge_eff", 0.90)
        es_loss_rate = cfg.get("es_loss_rate", 0.000125)
        hs_cs_charge_eff = cfg.get("hs_cs_charge_eff", 0.90)
        hs_cs_discharge_eff = cfg.get("hs_cs_discharge_eff", 0.90)
        hs_cs_loss_rate = cfg.get("hs_cs_loss_rate", 0.001)

        # 初始化能源系统模型
        logging.info("Initialize the energy system")
        self.date_time_index = pd.date_range(local_time, periods=time_step, freq="H")

        self.energy_system = solph.EnergySystem(
            timeindex=self.date_time_index
        )
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
            Sink(
                label="electricity demand",
                inputs={ele_bus: solph.Flow(fix=ele_load, nominal_value=1)},
            )
        )
        # 添加热负荷
        self.energy_system.add(
            Sink(
                label="heat demand",
                inputs={heat_bus: solph.Flow(fix=heat_demand, nominal_value=1)},
            )
        )
        # 添加冷负荷
        self.energy_system.add(
            Sink(
                label="cool demand",
                inputs={cool_bus: solph.Flow(fix=cool_demand, nominal_value=1)},
            )
        )
        # 设置电源参数
        grid = Source(
            label="grid",
            outputs={
                ele_bus: solph.Flow(nominal_value=10000000, variable_costs=ele_price)
            },
        )
        # 设置热源参数
        heat_source = Source(
            label="heat source",
            outputs={
                heat_bus: solph.Flow(nominal_value=1000000, variable_costs=10000000)
            },
        )
        # 设置冷源参数
        cool_source = Source(
            label="cool source",
            outputs={
                cool_bus: solph.Flow(nominal_value=1000000, variable_costs=10000000)
            },
        )
        # 设置气源参数
        gas = Source(
            label="gas",
            outputs={
                gas_bus: solph.Flow(nominal_value=10000000, variable_costs=gas_price)
            },
        )
        # 设置风电机组参数
        wt = Source(
            label="wind turbine",
            outputs={ele_bus: solph.Flow(fix=wt_output, nominal_value=1)},
        )
        # 设置光伏机组参数
        pv = Source(
            label="photovoltaic",
            outputs={ele_bus: solph.Flow(fix=pv_output, nominal_value=1)},
        )
        # 设置燃气轮机参数
        gt = Transformer(
            label="gas turbine",
            inputs={gas_bus: solph.Flow()},
            outputs={
                ele_bus: solph.Flow(nominal_value=gt_capacity),
                heat_bus: solph.Flow(nominal_value=gt_capacity * 1.5),
            },
            conversion_factors={ele_bus: gt_eta_e, heat_bus: gt_eta_h},
        )
        # 设置AC机组参数
        ac = Transformer(
            label="absorption chiller",
            inputs={heat_bus: solph.Flow(), ele_bus: solph.Flow()},
            outputs={cool_bus: solph.Flow(nominal_value=ac_capacity)},
            conversion_factors={cool_bus: ac_cop, heat_bus: ac_heat_ratio, ele_bus: ac_ele_ratio},
        )
        # 设置电热泵机组参数
        ehp = Transformer(
            label="electricity heat pump",
            inputs={ele_bus: solph.Flow()},
            outputs={heat_bus: solph.Flow(nominal_value=ehp_capacity)},
            conversion_factors={heat_bus: ehp_cop},
        )
        # 设置电制冷机组参数
        ec = Transformer(
            label="electricity chiller",
            inputs={ele_bus: solph.Flow()},
            outputs={cool_bus: solph.Flow(nominal_value=ec_capacity)},
            conversion_factors={cool_bus: ec_cop},
        )
        # 设置多余电出口参数
        ele_overflow = Sink(
            label="electricity overflow",
            inputs={ele_bus: solph.Flow(nominal_value=100000, variable_costs=0)},
        )
        # 设置多余热出口参数
        heat_overflow = Sink(
            label="heat overflow",
            inputs={heat_bus: solph.Flow(nominal_value=100000, variable_costs=0)},
        )
        # 设置多余冷出口参数
        cool_overflow = Sink(
            label="cool overflow",
            inputs={cool_bus: solph.Flow(nominal_value=100000, variable_costs=0)},
        )
        # 设置蓄电池机组参数
        ele_storage = GenericStorage(
            nominal_storage_capacity=ele_storage_io * 2,
            label="electricity storage",
            inputs={ele_bus: solph.Flow(nominal_value=ele_storage_io)},
            outputs={ele_bus: solph.Flow(nominal_value=ele_storage_io)},
            loss_rate=es_loss_rate,
            initial_storage_level=None,
            inflow_conversion_factor=es_charge_eff,
            outflow_conversion_factor=es_discharge_eff,
        )
        # 设置蓄热罐参数
        heat_storage = GenericStorage(
            nominal_storage_capacity=heat_storage_io * 4 / 3,
            label="heat storage",
            inputs={heat_bus: solph.Flow(nominal_value=heat_storage_io)},
            outputs={heat_bus: solph.Flow(nominal_value=heat_storage_io)},
            loss_rate=hs_cs_loss_rate,
            initial_storage_level=None,
            inflow_conversion_factor=hs_cs_charge_eff,
            outflow_conversion_factor=hs_cs_discharge_eff,
        )
        # 设置蓄冷罐参数
        cool_storage = GenericStorage(
            nominal_storage_capacity=cool_storage_io * 4 / 3,
            label="cool storage",
            inputs={cool_bus: solph.Flow(nominal_value=cool_storage_io)},
            outputs={cool_bus: solph.Flow(nominal_value=cool_storage_io)},
            loss_rate=hs_cs_loss_rate,
            initial_storage_level=None,
            inflow_conversion_factor=hs_cs_charge_eff,
            outflow_conversion_factor=hs_cs_discharge_eff,
        )
        # 将以上设备添加到系统中
        self.energy_system.add(
            wt,
            pv,
            gt,
            grid,
            ac,
            ehp,
            ec,
            gas,
            heat_source,
            cool_source,
            ele_overflow,
            heat_overflow,
            cool_overflow,
            ele_storage,
            heat_storage,
            cool_storage,
        )
        # ---- 卡诺电池（可选，equivalent planning model）----
        # 规划层 TI-CB 等效模型：
        #   - 仅用 GenericStorage 表达 电→储能→电 的对称等效往返链路
        #   - 不展开 HP-ORC 内部热力循环（详见 docs/辩论确认/carnot_battery_parameters_consensus.md）
        #   - 已删除旧版 "cb heat recovery" Transformer 支路（物理意义不成立）
        #   - E/P ∈ [4h, 8h] 约束在 cchp_gaproblem.py 中实施
        if cb_power > 0 and cb_capacity > 0:
            cb_rte = cfg.get("cb_rte", 0.60)
            cb_loss = cfg.get("cb_loss_rate", 0.002)   # 低中温TI-CB基准（从0.005下调）
            cb_charge_eff = cb_rte ** 0.5    # 对称分配 ~0.775
            cb_discharge_eff = cb_rte ** 0.5

            carnot_battery = GenericStorage(
                nominal_storage_capacity=cb_capacity,
                label="carnot battery",
                inputs={ele_bus: solph.Flow(nominal_value=cb_power)},
                outputs={ele_bus: solph.Flow(nominal_value=cb_power)},
                loss_rate=cb_loss,
                initial_storage_level=None,
                inflow_conversion_factor=cb_charge_eff,
                outflow_conversion_factor=cb_discharge_eff,
            )
            self.energy_system.add(carnot_battery)
        # 初始化模型
        model = solph.Model(self.energy_system)
        # # 创建求解计算电网电功率最大值的子模型
        # max_ele_load_block = po.Block()
        # # 将子模型添加到主模型中
        # model.add_component("max_ele_load_block", max_ele_load_block)
        # # 设置变量
        # model.max_ele_load_block.max_load = po.Var(model.TIMESTEPS, domain=po.NonNegativeReals)
        # model.max_ele_load_block.max_load_upper_switch = po.Var(model.TIMESTEPS, within=po.Binary)
        # big_number = 100000000
        #
        # # 设置计算功率下限约束规则
        # def max_ele_load_lower(m, s, e, t):
        #     return model.max_ele_load_block.max_load[0] >= model.flow[s, e, t]
        #
        # # 设置计算功率上限约束规则
        # def max_ele_load_upper(m, s, e, t):
        #     return model.max_ele_load_block.max_load[0] <= \
        #            model.flow[s, e, t] + big_number * (1 - model.max_ele_load_block.max_load_upper_switch[t])
        #
        # # 添加求解计算功率最大值的约束
        # model.max_ele_load_block.max_load_lower_constr = po.Constraint(
        #     [(grid, ele_bus)], model.TIMESTEPS, rule=max_ele_load_lower)
        # model.max_ele_load_block.max_load_upper_constr = po.Constraint(
        #     [(grid, ele_bus)], model.TIMESTEPS, rule=max_ele_load_upper)
        # model.max_ele_load_block.max_load_upper_switch_constr = po.Constraint(
        #     rule=(sum(model.max_ele_load_block.max_load_upper_switch[t] for t in model.TIMESTEPS) >= 1))
        #
        # # 定义考虑容量费的目标函数
        # objective_expr = 0
        # for t in model.TIMESTEPS:
        #     objective_expr += (model.flows[gas, gas_bus].variable_costs[t] * model.flow[gas, gas_bus, t]
        #                        + model.flows[grid, ele_bus].variable_costs[t] * model.flow[grid, ele_bus, t]
        #                        + model.flows[heat_source, heat_bus].variable_costs[t] * model.flow[heat_source, heat_bus, t]
        #                        + model.flows[cool_source, cool_bus].variable_costs[t] * model.flow[cool_source, cool_bus, t])
        # objective_expr += 16.7 * model.max_ele_load_block.max_load[0]
        # model.del_component('objective')
        # model.objective = po.Objective(expr=objective_expr)
        self.model = model

    # 模型优化与储存
    def optimise(self) -> None:
        solver_verbose = False  # 是否输出求解器信息
        _solve_model_with_priority(self, solver_verbose)

    # 返回优化结果
    def get_objective_value(self):
        return self.energy_system.results["meta"]["objective"]

    # 返回设备出力数据
    def get_complementary_results(self):
        complementary_results = dict()
        results = self.energy_system.results["main"]
        symbols = [
            "grid",
            "electricity overflow",
            "heat source",
            "heat overflow",
            "cool source",
            "cool overflow",
        ]
        for symbol in symbols:
            node = solph.views.node(results, symbol)
            flows = node["sequences"].columns
            flow_list = []
            for f in flows:
                flow_list = np.array(node["sequences"][f]).tolist()
            # 截取前 time_step 个数据，忽略 infer_last_interval=True 产生的最后一个点
            complementary_results[symbol] = flow_list[: self.time_step]
        return complementary_results

    # 备份结果
    def dump_result(self):
        # 保存结果
        logging.info("Store the energy system with the results.")
        self.energy_system.dump(dpath=self.log_path, filename=None)

    # 结果展示
    def result_process(self, bus_name, save_path=None):
        results = self.energy_system.results["main"]
        # 获取需要展示的节点
        show_bus = solph.views.node(results, bus_name)
        # 绘制母线输入输出图像
        ele_flows = show_bus["sequences"].columns
        bottom1 = [0] * len(self.date_time_index)
        bottom2 = [0] * len(self.date_time_index)
        fig, ax = plt.subplots(figsize=(8, 5))
        for flow in ele_flows:
            if flow[0][0] != bus_name:
                ax.bar(
                    self.date_time_index,
                    show_bus["sequences"][flow],
                    0.03,
                    bottom=bottom1,
                    label=flow[0][0] + " to " + flow[0][1],
                )
                bottom1 = [
                    (a + b) for a, b in zip(show_bus["sequences"][flow], bottom1)
                ]
            else:
                bottom2 = [
                    (a - b) for a, b in zip(bottom2, show_bus["sequences"][flow])
                ]
                ax.bar(
                    self.date_time_index,
                    show_bus["sequences"][flow],
                    0.03,
                    bottom=bottom2,
                    label=flow[0][0] + " to " + flow[0][1],
                )
        plt.legend(
            loc="upper center",
            prop={"size": 7},
            bbox_to_anchor=(0.5, 1.25),
            ncol=3,
        )
        ax.set_yticks(
            np.linspace(
                min(bottom2) + 0.1 * min(bottom2),
                max(bottom1) + 0.1 * max(bottom1),
                13,
                endpoint=True,
            )
        )
        plt.xlabel("t/h")
        plt.ylabel("P/kW")

        if save_path:
            plt.savefig(save_path)
            print(f"Plot saved to {save_path}")
            plt.close()  # Close to avoid memory leak or display if not needed
        else:
            plt.show()

        # 输出求解结果
        print("********* Meta results *********")
        pp.pprint(self.energy_system.results["meta"])
        print("")
        # 输出各个母线的输入输出总量
        print("********* Main results *********")
        print(show_bus["sequences"].sum(axis=0))


class HeatEleModel:
    """
    分布式电热综合能源系统调度模型
    -------------------
    园区能源拓扑结构（简化为电热两种能流）：
                      input/output  ele_bus  heat_bus  gas_bus
                            |          |         |         |
     wt(FixedSource)        |--------->|         |         |
                            |          |         |         |
     pv(FixedSource)        |--------->|         |         |
                            |          |         |         |
     gas(Commodity)         |----------------------------->|
                            |          |         |         |
     grid(Commodity)        |--------->|         |         |
                            |          |         |         |
     ele_demand(Sink)       |<---------|         |         |
                            |          |         |         |
     heat_demand(Sink)      |<-------------------|         |
                            |          |         |         |
                            |<-----------------------------|
     gt(Transformer)        |--------->|         |         |  (CHP: 热电联产)
                            |------------------->|         |
                            |          |         |         |
     ehp(Transformer)       |<---------|         |         |
                            |------------------->|         |
                            |          |         |         |
     es(Storage)            |<---------|         |         |
                            |--------->|         |         |
                            |          |         |         |
     hs(Storage)            |<-------------------|         |
                            |------------------->|         |
                      input/output  ele_bus  heat_bus  gas_bus
    符号说明：
    wt - wind turbine (风电)
    pv - photovoltaic (光伏)
    gas - natural gas (天然气)
    grid - grid electricity (电网)
    ele_demand - electricity demand (电负荷)
    heat_demand - heat demand (热负荷)
    gt - gas turbine CHP (燃气轮机热电联产)
    ehp - electricity heat pump (电热泵)
    es - electricity storage (电储能)
    hs - heat storage (热储能)
    """

    def __init__(
        self,
        local_time,
        time_step,
        ele_price,
        gas_price,
        ele_load,
        heat_demand,
        wt_output,
        pv_output,
        gt_capacity,  # 燃气轮机CHP容量
        ehp_capacity,  # 电热泵容量
        ele_storage_io,  # 电储能功率
        heat_storage_io,  # 热储能功率
    ):
        self.time_step = time_step
        # 保存输入数据用于后续源荷匹配度计算
        self.ele_load = ele_load
        self.heat_demand_input = heat_demand
        self.wt_output = wt_output
        self.pv_output = pv_output

        # 初始化能源系统模型
        logging.info("Initialize the heat-electricity energy system")
        self.date_time_index = pd.date_range(local_time, periods=time_step, freq="H")

        self.energy_system = solph.EnergySystem(
            timeindex=self.date_time_index
        )

        ##########################################################################
        # 创建能源系统设备对象
        ##########################################################################
        logging.info("Create oemof objects for heat-electricity system")

        # 创建电母线
        ele_bus = solph.Bus(label="electricity bus")
        # 创建热母线
        heat_bus = solph.Bus(label="heat bus")
        # 创建气母线
        gas_bus = solph.Bus(label="gas bus")
        # 将母线添加到模型中
        self.energy_system.add(ele_bus, heat_bus, gas_bus)

        # 添加电负荷
        self.energy_system.add(
            Sink(
                label="electricity demand",
                inputs={ele_bus: solph.Flow(fix=ele_load, nominal_value=1)},
            )
        )
        # 添加热负荷
        self.energy_system.add(
            Sink(
                label="heat demand",
                inputs={heat_bus: solph.Flow(fix=heat_demand, nominal_value=1)},
            )
        )

        # 设置电网参数（可购电）
        grid = Source(
            label="grid",
            outputs={
                ele_bus: solph.Flow(nominal_value=10000000, variable_costs=ele_price)
            },
        )

        # 设置备用热源参数（惩罚性热源，用于保证系统可行性）
        heat_source = Source(
            label="heat source",
            outputs={
                heat_bus: solph.Flow(nominal_value=1000000, variable_costs=10000000)
            },
        )

        # 设置气源参数
        gas = Source(
            label="gas",
            outputs={
                gas_bus: solph.Flow(nominal_value=10000000, variable_costs=gas_price)
            },
        )

        # 设置风电机组参数
        wt = Source(
            label="wind turbine",
            outputs={ele_bus: solph.Flow(fix=wt_output, nominal_value=1)},
        )

        # 设置光伏机组参数
        pv = Source(
            label="photovoltaic",
            outputs={ele_bus: solph.Flow(fix=pv_output, nominal_value=1)},
        )

        # 设置燃气轮机CHP参数（热电联产）
        gt = Transformer(
            label="gas turbine",
            inputs={gas_bus: solph.Flow()},
            outputs={
                ele_bus: solph.Flow(nominal_value=gt_capacity),
                heat_bus: solph.Flow(nominal_value=gt_capacity * 1.5),
            },
            conversion_factors={ele_bus: 0.33, heat_bus: 0.5},
        )

        # 设置电热泵机组参数
        ehp = Transformer(
            label="electricity heat pump",
            inputs={ele_bus: solph.Flow()},
            outputs={heat_bus: solph.Flow(nominal_value=ehp_capacity)},
            conversion_factors={heat_bus: 4.0},  # COP = 4.0
        )

        # 燃气锅炉暂时注释（缺少准确参数数据）
        # gb = Transformer(
        #     label="gas boiler",
        #     inputs={gas_bus: solph.Flow()},
        #     outputs={heat_bus: solph.Flow(nominal_value=gb_capacity)},
        #     conversion_factors={heat_bus: 0.9},  # 效率90%
        # )

        # 设置多余电出口参数（弃电/上网）
        ele_overflow = Sink(
            label="electricity overflow",
            inputs={ele_bus: solph.Flow(nominal_value=100000, variable_costs=0)},
        )

        # 设置多余热出口参数（弃热）
        heat_overflow = Sink(
            label="heat overflow",
            inputs={heat_bus: solph.Flow(nominal_value=100000, variable_costs=0)},
        )

        # 设置蓄电池机组参数
        ele_storage = GenericStorage(
            nominal_storage_capacity=ele_storage_io * 2,
            label="electricity storage",
            inputs={ele_bus: solph.Flow(nominal_value=ele_storage_io)},
            outputs={ele_bus: solph.Flow(nominal_value=ele_storage_io)},
            loss_rate=0.000125,
            initial_storage_level=None,
            inflow_conversion_factor=0.95,
            outflow_conversion_factor=0.90,
        )

        # 设置蓄热罐参数
        heat_storage = GenericStorage(
            nominal_storage_capacity=heat_storage_io * 4 / 3,
            label="heat storage",
            inputs={heat_bus: solph.Flow(nominal_value=heat_storage_io)},
            outputs={heat_bus: solph.Flow(nominal_value=heat_storage_io)},
            loss_rate=0.001,
            initial_storage_level=None,
            inflow_conversion_factor=0.9,
            outflow_conversion_factor=0.9,
        )

        # 将以上设备添加到系统中
        self.energy_system.add(
            wt,
            pv,
            gt,
            grid,
            ehp,
            # gb,  # 燃气锅炉暂时注释
            gas,
            heat_source,
            ele_overflow,
            heat_overflow,
            ele_storage,
            heat_storage,
        )

        # 初始化模型
        self.model = solph.Model(self.energy_system)

    def optimise(self) -> None:
        """Solve the optimisation model."""
        solver_verbose = False
        _solve_model_with_priority(self, solver_verbose)

    def get_objective_value(self):
        """返回优化结果（运行成本）"""
        return self.energy_system.results["meta"]["objective"]

    def get_complementary_results(self):
        """返回用于计算源荷匹配度的设备出力数据"""
        complementary_results = dict()
        results = self.energy_system.results["main"]
        symbols = [
            "grid",
            "electricity overflow",
            "heat source",
            "heat overflow",
        ]
        for symbol in symbols:
            node = solph.views.node(results, symbol)
            flows = node["sequences"].columns
            flow_list = []
            for f in flows:
                flow_list = np.array(node["sequences"][f]).tolist()
            complementary_results[symbol] = flow_list[: self.time_step]
        return complementary_results

    def get_detailed_results(self):
        """
        返回详细的设备出力结果，用于源荷匹配度分析
        包含：可再生能源出力、各设备出力、储能状态等
        """
        detailed_results = dict()
        results = self.energy_system.results["main"]

        # 获取各设备的出力
        device_labels = [
            "wind turbine",
            "photovoltaic",
            "gas turbine",
            "electricity heat pump",
            "gas boiler",
            "grid",
            "electricity storage",
            "heat storage",
        ]

        for label in device_labels:
            try:
                node = solph.views.node(results, label)
                detailed_results[label] = node["sequences"]
            except:
                pass

        return detailed_results

    def calc_source_load_matching_pearson(self):
        """
        计算基于Pearson相关系数的源荷匹配度

        源荷匹配度定义：可再生能源出力与负荷需求的时序相关性
        SLMD = (ρ_ele + ρ_heat) / 2
        其中：
        - ρ_ele: 可再生能源电出力与电负荷的Pearson相关系数
        - ρ_heat: 热源出力与热负荷的Pearson相关系数

        返回值越接近1，表示源荷匹配度越好
        返回值为负表示源荷反向波动（不匹配）
        """
        # 可再生能源电出力 = 风电 + 光伏
        re_output = np.array(self.wt_output) + np.array(self.pv_output)
        ele_load = np.array(self.ele_load)
        heat_load = np.array(self.heat_demand_input)

        # 计算电侧Pearson相关系数：可再生能源出力与电负荷的相关性
        if np.std(re_output) > 1e-6 and np.std(ele_load) > 1e-6:
            rho_ele = np.corrcoef(re_output, ele_load)[0, 1]
        else:
            rho_ele = 0.0

        # 计算热侧Pearson相关系数：可再生能源出力与热负荷的相关性
        # 电热耦合系统中，可再生能源可通过电热泵转化为热能
        if np.std(re_output) > 1e-6 and np.std(heat_load) > 1e-6:
            rho_heat = np.corrcoef(re_output, heat_load)[0, 1]
        else:
            rho_heat = 0.0

        # 综合源荷匹配度 = 电热相关系数的加权平均
        # 权重可根据电热负荷比例调整
        ele_weight = np.sum(ele_load) / (np.sum(ele_load) + np.sum(heat_load) + 1e-6)
        heat_weight = 1 - ele_weight
        slmd = ele_weight * rho_ele + heat_weight * rho_heat

        return slmd

    def calc_source_load_matching_std(self):
        """
        计算基于净负荷标准差的源荷匹配度（与原代码兼容）

        净负荷 = 外部输入 - 弃能
        标准差越小，表示系统波动越小，源荷匹配度越好
        """
        results = self.get_complementary_results()

        net_ele_load = np.array(results["grid"]) - np.array(
            results["electricity overflow"]
        )
        net_heat_load = np.array(results["heat source"]) - np.array(
            results["heat overflow"]
        )

        # 源荷匹配度 = 电净负荷标准差 + 热净负荷标准差
        slmd = np.std(net_ele_load) + np.std(net_heat_load)

        return slmd

    def calc_source_load_matching_ltpr(self):
        """
        计算基于负荷跟踪偏差率的源荷匹配度 (Load Tracking Performance Rate)

        LTPR = 1 - (1/T) * Σ|P_re(t) - P_load(t)| / P_load_max

        返回值越接近1，表示源荷匹配度越好
        """
        re_output = np.array(self.wt_output) + np.array(self.pv_output)
        ele_load = np.array(self.ele_load)

        if np.max(ele_load) > 1e-6:
            deviation = np.mean(np.abs(re_output - ele_load)) / np.max(ele_load)
            ltpr = 1 - deviation
        else:
            ltpr = 0

        return ltpr

    def result_process(self, bus_name, save_path=None):
        """结果展示"""
        results = self.energy_system.results["main"]
        show_bus = solph.views.node(results, bus_name)

        ele_flows = show_bus["sequences"].columns
        bottom1 = [0] * len(self.date_time_index)
        bottom2 = [0] * len(self.date_time_index)
        fig, ax = plt.subplots(figsize=(10, 6))

        for flow in ele_flows:
            if flow[0][0] != bus_name:
                ax.bar(
                    self.date_time_index,
                    show_bus["sequences"][flow],
                    0.03,
                    bottom=bottom1,
                    label=flow[0][0] + " → " + flow[0][1],
                )
                bottom1 = [
                    (a + b) for a, b in zip(show_bus["sequences"][flow], bottom1)
                ]
            else:
                bottom2 = [
                    (a - b) for a, b in zip(bottom2, show_bus["sequences"][flow])
                ]
                ax.bar(
                    self.date_time_index,
                    show_bus["sequences"][flow],
                    0.03,
                    bottom=bottom2,
                    label=flow[0][0] + " → " + flow[0][1],
                )

        plt.legend(
            loc="upper center",
            prop={"size": 8},
            bbox_to_anchor=(0.5, 1.20),
            ncol=3,
        )
        ax.set_yticks(
            np.linspace(
                min(bottom2) + 0.1 * min(bottom2) if min(bottom2) < 0 else 0,
                max(bottom1) + 0.1 * max(bottom1),
                11,
                endpoint=True,
            )
        )
        plt.xlabel("时间 (h)")
        plt.ylabel("功率 (kW)")
        plt.title(f"{bus_name} 功率平衡图")
        plt.grid(True, alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"Plot saved to {save_path}")
            plt.close()
        else:
            plt.show()

        print("********* Meta results *********")
        pp.pprint(self.energy_system.results["meta"])
        print("")
        print("********* Main results *********")
        print(show_bus["sequences"].sum(axis=0))
