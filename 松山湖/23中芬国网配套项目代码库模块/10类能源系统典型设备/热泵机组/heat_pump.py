"""
HeatPump class subclass
"""

import CoolProp.CoolProp as CoolProp
import matplotlib.pyplot as plt

from fluprodia import FluidPropertyDiagram
from tespy.components import CycleCloser, Compressor, MovingBoundaryHeatExchanger, Valve, Subsystem, Source, Sink
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine, load_default_char as ldc

from utils import SubsystemParameters, csv_to_params, RefpropWrapper


class HeatPump(Subsystem):
    """
    Create a heat pump subsystem

    Attributes:
    label: str
        The label of the subsystem.
    params: SubsystemParameters

    Methods:
    create_comps():
        Create the components of the subsystem.
    create_conns():
        Create the connections of the subsystem.
    initialize():
        Initialize the subsystem.
    set_design():
        Set the design parameters of the subsystem.
    calc_performance():
        Calculate the performance of the subsystem.
    plot_h_p_diagram():
        Plot the h-p diagram of the subsystem.

    """

    # initialize the subsystem
    def __init__(self, label, params: SubsystemParameters):
        """Initialize the heat pump subsystem"""
        Subsystem.__init__(self, label)
        self.params = params
        self.performance = {}
        self.buses = {}
        self.create_comps()
        self.create_conns()
        self.set_inner_params()

    def create_comps(self):
        """Create the subsystem's components."""
        self.comps['cycle_closer'] = CycleCloser('HP Cycle Closer')
        self.comps['evap'] = MovingBoundaryHeatExchanger('HP Evaporator')
        self.comps['comp'] = Compressor('HP Compressor')
        self.comps['cond'] = MovingBoundaryHeatExchanger('HP Condenser')
        self.comps['valve'] = Valve('HP Expansion Valve')
        return None

    def update_params(self, params_new):
        self.params = params_new

    def create_conns(self):
        """Create the subsystem's connections."""
        self.conns['c0'] = Connection(
            self.comps['valve'], 'out1', self.comps['cycle_closer'], 'in1', label='0')
        self.conns['c1'] = Connection(
            self.comps['cycle_closer'], 'out1', self.comps['evap'], 'in2', label='1')
        self.conns['c2'] = Connection(
            self.comps['evap'], 'out2', self.comps['comp'], 'in1', label='2')
        self.conns['c3'] = Connection(
            self.comps['comp'], 'out1', self.comps['cond'], 'in1', label='3')
        self.conns['c4'] = Connection(
            self.comps['cond'], 'out1', self.comps['valve'], 'in1', label='4')
        return None

    def add_outer_conns(self):
        """
        在网络中初始化热泵子系统
        :return:  None
        """
        # 添加边界点
        self.comps['heat_source_in'] = Source('Heat Source Inlet')
        self.comps['heat_source_out'] = Sink('Heat Source Outlet')
        self.comps['cold_storage_out'] = Source('Cold Storage Outlet')
        self.comps['hot_storage_in'] = Sink('Hot Storage Inlet')

        # 添加连接
        self.conns['c11'] = Connection(self.comps['heat_source_in'], 'out1', self.comps['evap'], 'in1', label='11')
        self.conns['c12'] = Connection(self.comps['evap'], 'out1', self.comps['heat_source_out'], 'in1', label='12')
        self.conns['c21'] = Connection(self.comps['cold_storage_out'], 'out1', self.comps['cond'], 'in2', label='21')
        self.conns['c22'] = Connection(self.comps['cond'], 'out2', self.comps['hot_storage_in'], 'in1', label='22')

    def set_inner_params(self):
        """Initialize the subsystem."""
        self.params.cold_storage_out_temp = self.params.cold_storage_temp

        self.conns['c0'].set_attr(fluid={self.params.hp_cycle_fluid_type: 1},
                                  fluid_engines={self.params.hp_cycle_fluid_type: RefpropWrapper})
        if (self.params.hp_temp_evap and self.params.hp_temp_cond
                and self.params.hp_superheat_degree):
            self.conns['c2'].set_attr(
                Td_bp=self.params.hp_superheat_degree,
                p=CoolProp.PropsSI('P', 'T', self.params.hp_temp_evap + 273.15,
                                   'Q', 1, self.params.hp_cycle_fluid_type)
            )
            supercool_degree_guess = self.params.hp_temp_cond - self.params.cold_storage_out_temp - self.params.pinch_point_temp
            self.conns['c4'].set_attr(
                Td_bp=- supercool_degree_guess,
                p=CoolProp.PropsSI('P', 'T', self.params.hp_temp_cond + 273.15,
                                   'Q', 1, self.params.hp_cycle_fluid_type)
            )
        else:
            try:
                hp_fluid = RefpropWrapper(self.params.hp_cycle_fluid_type)
                hp_temp_evap_guess = self.params.heat_source_out_temp - self.params.pinch_point_temp

                is_valid = (self.params.hp_superheat_degree < self.params.heat_source_in_temp - hp_temp_evap_guess)
                if not is_valid:
                    raise ValueError("HP过热度越限")

                hp_pressure_evap = hp_fluid.p_sat(hp_temp_evap_guess + 273.15)
                self.conns['c2'].set_attr(
                    Td_bp=self.params.hp_superheat_degree,
                    p=hp_pressure_evap,
                )

                # 蒸发温度存在较大优化空间
                hp_temp_cond_guess = self.params.hot_storage_temp + self.params.pinch_point_temp
                # 过冷度也存在较大优化空间
                hp_supercool_degree_guess = hp_temp_cond_guess - self.params.cold_storage_temp - self.params.pinch_point_temp
                hp_pressure_cond = hp_fluid.p_sat(hp_temp_cond_guess + 273.15)
                self.conns['c4'].set_attr(
                    Td_bp=- hp_supercool_degree_guess,
                    p=hp_pressure_cond,
                )
            except Exception as e:
                print(f"模拟运行错误: {str(e)}")
                raise
        kA_char_default = ldc("heat exchanger", "kA_char1", "DEFAULT", CharLine)
        kA_char_cond = ldc("heat exchanger", "kA_char1", "CONDENSING FLUID", CharLine)
        kA_char_evap = ldc("heat exchanger", "kA_char2", "EVAPORATING FLUID", CharLine)
        comp_eta_s_char = ldc("compressor", "eta_s_char", "DEFAULT", CharLine)

        self.comps['evap'].set_attr(pr1=self.params.pressure_rate, pr2=self.params.pressure_rate,
                                    kA_char1=kA_char_default, kA_char2=kA_char_evap,
                                    design=['pr1', 'pr2', 'td_pinch'], offdesign=['zeta1', 'zeta2', 'kA_char'])
        self.comps['comp'].set_attr(eta_s=self.params.comp_eta_s,
                                    eta_s_char=comp_eta_s_char,
                                    design=['eta_s'], offdesign=['eta_s_char'])
        self.comps['cond'].set_attr(pr1=self.params.pressure_rate, pr2=self.params.pressure_rate,
                                    kA_char1=kA_char_cond, kA_char2=kA_char_default,
                                    design=['pr1', 'pr2', 'td_pinch'], offdesign=['zeta1', 'zeta2', 'kA_char'])

    def set_outer_params(self):
        # 质量流量指定方式
        if self.params.hp_mass_flow:
            self.conns['c0'].set_attr(m=self.params.hp_mass_flow)
        elif self.params.heat_source_in_mass_flow:
            self.conns['c11'].set_attr(m=self.params.heat_source_in_mass_flow)
        elif self.params.charge_mass_flow:
            self.conns['c21'].set_attr(m=self.params.charge_mass_flow)
        else:
            raise ValueError('Mass flow rate of Heat Pump not specified')

        # -------------------- 热源侧 --------------------
        self.conns['c11'].set_attr(T=self.params.heat_source_in_temp,
                                   p=self.params.heat_source_in_pressure,
                                   fluid={self.params.heat_source_fluid_type: 1})
        self.conns['c12'].set_attr(T=self.params.heat_source_out_temp)
        # -------------------- 储热侧 --------------------
        self.params.hot_storage_in_temp = self.params.hot_storage_temp
        self.params.cold_storage_out_temp = self.params.cold_storage_temp
        self.conns['c21'].set_attr(T=self.params.cold_storage_temp,
                                   p=self.params.cold_storage_out_pressure,
                                   fluid={self.params.heat_storage_fluid_type: 1}
                                   )
        self.conns['c22'].set_attr(T=self.params.hot_storage_in_temp)
        return None

    def set_design_params(self):
        """Set the design parameters of the subsystem."""
        if self.params.hp_temp_evap and self.params.hp_temp_cond and self.params.hp_superheat_degree:
            self.comps['evap'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c2'].set_attr(p=None)
            self.comps['cond'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c4'].set_attr(p=None)
        else:
            self.comps['evap'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c2'].set_attr(p=None)
            self.comps['cond'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c4'].set_attr(p=None)
        return None

    def calc_performance(self):
        """Calculate the performance of the subsystem."""
        self.performance['q_(in)^(hp)'] = abs(self.comps['evap'].Q.val) / 1e3 / self.conns['c1'].m.val_SI
        self.performance['Q_(in)^(hp)'] = abs(self.comps['evap'].Q.val) / 1e3
        self.performance['q_(out)^(hp)'] = abs(self.comps['cond'].Q.val) / 1e3 / self.conns['c1'].m.val_SI
        self.performance['Q_(out)^(hp)'] = abs(self.comps['cond'].Q.val) / 1e3
        self.performance['w^(comp)'] = self.comps['comp'].P.val / self.params.motor_eta / 1e3 / self.conns['c1'].m.val_SI
        self.performance['W^(comp)'] = self.comps['comp'].P.val / self.params.motor_eta / 1e3
        self.performance['COP'] = self.performance['q_(out)^(hp)'] / self.performance['w^(comp)']
        return None

    def exergy_simple(self):
        T_amb = 293.15
        P_amb = 101325
        h_0 = CoolProp.PropsSI('H', 'T', T_amb, 'P', P_amb, 'water')
        s_0 = CoolProp.PropsSI('S', 'T', T_amb, 'P', P_amb, 'water')
        hs_exergy_in = self.conns['c11'].m.val * (self.conns['c11'].h.val - h_0 - T_amb * (self.conns['c11'].s.val - s_0))
        hs_exergy_out = self.conns['c12'].m.val * (self.conns['c12'].h.val - h_0 - T_amb * (self.conns['c12'].s.val - s_0))
        hs_exergy_fuel = hs_exergy_in - hs_exergy_out
        return hs_exergy_fuel

    def plot_h_p_diagram(self):
        """Plot the h-log(p) diagram of the subsystem."""
        # 有bug
        pass
        # 记录数据
        result_dict = {}
        result_dict.update({self.comps['evap'].label: self.comps['evap'].get_plotting_data()[2]})
        result_dict.update({self.comps['comp'].label: self.comps['comp'].get_plotting_data()[1]})
        result_dict.update({self.comps['cond'].label: self.comps['cond'].get_plotting_data()[1]})
        result_dict.update({self.comps['valve'].label: self.comps['valve'].get_plotting_data()[1]})

        # 绘图
        diagram = FluidPropertyDiagram(self.params.hp_cycle_fluid_type)
        diagram.set_unit_system(T='°C', p='Pa', h='J/kg')

        for key, data in result_dict.items():
            result_dict[key]['datapoints'] = diagram.calc_individual_isoline(**data)

        diagram.calc_isolines()

        fig, ax = plt.subplots(1, figsize=(16, 10))
        # 找到result_dict[key]['datapoints']['h']的最大值
        h_max = max([max(result_dict[key]['datapoints']['h']) for key in result_dict.keys()])
        # 找到result_dict[key]['datapoints']['p']的最大值
        p_max = max([max(result_dict[key]['datapoints']['p']) for key in result_dict.keys()])

        diagram.draw_isolines(fig, ax, 'logph', x_min=0, x_max=h_max * 2, y_min=p_max / 10, y_max=p_max * 10)

        for key in result_dict.keys():
            datapoints = result_dict[key]['datapoints']
            ax.plot(datapoints['h'], datapoints['p'], color='#ff1100')
            ax.scatter(datapoints['h'][0], datapoints['p'][0], color='#ff0000')

        plt.tight_layout()
        fig.show()
        fig.savefig('../results/heat_pump_logph')


if __name__ == "__main__":
    # 参数
    params_path = '../results/params/params_validation_refactored.csv'
    params_test = csv_to_params(params_path)
    hp_test = HeatPump('Heat Pump', params_test)
    hp_test.add_outer_conns()
    hp_test.set_outer_params()
    print('hp initialized')
