"""
Organic Rankine cycle subsystem

Attributes:
label: str
    The label of the subsystem.
params: SubsystemParameters

"""

import CoolProp.CoolProp as CoolProp
import matplotlib.pyplot as plt

from fluprodia import FluidPropertyDiagram
from tespy.components import CycleCloser, Turbine, Pump, MovingBoundaryHeatExchanger, Subsystem, Source, Sink
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine, load_default_char as ldc

from utils import SubsystemParameters, csv_to_params, RefpropWrapper


class OrganicRankineCycle(Subsystem):
    """
    Create an organic Rankine cycle subsystem

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
        Plot the h-log(p) diagram of the subsystem.
    """

    def __init__(self, label, params: SubsystemParameters):
        """Initialize the organic Rankine cycle subsystem"""
        Subsystem.__init__(self, label)
        self.params = params
        self.create_comps()
        self.create_conns()
        self.set_inner_params()
        self.performance = {}

    def update_params(self, params_new):
        self.params = params_new

    def create_comps(self):
        """Create the subsystem's components."""
        self.comps['cycle_closer'] = CycleCloser('ORC Cycle Closer')
        self.comps['evap'] = MovingBoundaryHeatExchanger('ORC Evaporator')
        self.comps['turb'] = Turbine('ORC Turbine')
        self.comps['cond'] = MovingBoundaryHeatExchanger('ORC Condenser')
        self.comps['pump'] = Pump('ORC Pump')
        return None

    def create_conns(self):
        """Create the subsystem's connections."""
        self.conns['c00'] = Connection(
            self.comps['pump'], 'out1', self.comps['cycle_closer'], 'in1', label='99')
        self.conns['c5'] = Connection(
            self.comps['cycle_closer'], 'out1', self.comps['evap'], 'in2', label='5')
        self.conns['c6'] = Connection(
            self.comps['evap'], 'out2', self.comps['turb'], 'in1', label='6')
        self.conns['c7'] = Connection(
            self.comps['turb'], 'out1', self.comps['cond'], 'in1', label='7')
        self.conns['c8'] = Connection(
            self.comps['cond'], 'out1', self.comps['pump'], 'in1', label='8')
        return None

    def add_outer_conns(self):
        """
        在网络中初始化有机朗肯循环子系统
        :return:  None
        """
        # 储热侧与冷却水侧
        self.comps['hot_storage_out'] = Source('Hot Storage Outlet')
        self.comps['cold_storage_in'] = Sink('Cold Storage Inlet')
        self.comps['cold_source_in'] = Source('Cold Source Inlet')
        self.comps['cold_source_out'] = Sink('Cold Source Outlet')

        # 添加所有组件与连接
        self.conns['c23'] = Connection(self.comps['hot_storage_out'], 'out1', self.comps['evap'], 'in1', label='23')
        self.conns['c24'] = Connection(self.comps['evap'], 'out1', self.comps['cold_storage_in'], 'in1', label='24')
        self.conns['c31'] = Connection(self.comps['cold_source_in'], 'out1', self.comps['cond'], 'in2', label='31')
        self.conns['c32'] = Connection(self.comps['cond'], 'out2', self.comps['cold_source_out'], 'in1', label='32')

        return None

    def set_inner_params(self):
        """Initialize the subsystem."""
        self.conns['c00'].set_attr(fluid={self.params.orc_cycle_fluid_type: 1},
                                   fluid_engines={self.params.orc_cycle_fluid_type: RefpropWrapper})
        if (self.params.orc_temp_evap and self.params.orc_temp_cond
                and self.params.orc_superheat_degree):
            self.conns['c6'].set_attr(Td_bp=self.params.orc_superheat_degree,
                                      p=CoolProp.PropsSI('P', 'T', self.params.orc_temp_evap + 273.15,
                                                         'Q', 0, self.params.orc_cycle_fluid_type
                                                         )
                                      )
            self.conns['c8'].set_attr(
                Td_bp=-2,
                p=CoolProp.PropsSI('P', 'T', self.params.orc_temp_cond + 273.15,
                                   'Q', 1, self.params.orc_cycle_fluid_type)
            )
        else:
            try:
                orc_fluid = RefpropWrapper(self.params.orc_cycle_fluid_type)
                orc_temp_evap_guess = self.params.cold_storage_temp - self.params.pinch_point_temp

                is_valid = (self.params.orc_superheat_degree < self.params.hot_storage_temp - orc_temp_evap_guess)
                if not is_valid:
                    raise ValueError("ORC过热度越限")

                orc_pressure_evap = orc_fluid.p_sat(orc_temp_evap_guess + 273.15)
                self.conns['c6'].set_attr(
                    Td_bp=self.params.orc_superheat_degree,
                    p=orc_pressure_evap,
                )

                # ?
                orc_temp_cond_guess = self.params.cold_source_in_temp + self.params.pinch_point_temp
                # 仅保证液相
                orc_supercool_degree_guess = 2
                orc_pressure_cond = orc_fluid.p_sat(orc_temp_cond_guess + 273.15)
                self.conns['c8'].set_attr(
                    Td_bp=-orc_supercool_degree_guess,
                    p=orc_pressure_cond,
                )
                pass
            except Exception as e:
                print(f"模拟运行错误: {str(e)}")
                raise

        # 设定设备参数
        kA_char_default = ldc("heat exchanger", "kA_char1", "DEFAULT", CharLine)
        kA_char_cond = ldc("heat exchanger", "kA_char1", "CONDENSING FLUID", CharLine)
        kA_char_evap = ldc("heat exchanger", "kA_char2", "EVAPORATING FLUID", CharLine)
        turb_eta_s_char = ldc("turbine", "eta_s_char", "TRAUPEL", CharLine)
        pump_eta_s_char = ldc("pump", "eta_s_char", "DEFAULT", CharLine)

        # 设定设备参数
        self.comps['evap'].set_attr(pr1=self.params.pressure_rate, pr2=self.params.pressure_rate,
                                    kA_char1=kA_char_default, kA_char2=kA_char_evap,
                                    design=['pr1', 'pr2', 'td_pinch'], offdesign=['zeta1', 'zeta2', 'kA_char'])
        self.comps['turb'].set_attr(eta_s=self.params.turb_eta_s,
                                    eta_s_char=turb_eta_s_char,
                                    design=['eta_s'], offdesign=['eta_s_char'])
        self.comps['cond'].set_attr(pr1=self.params.pressure_rate, pr2=self.params.pressure_rate,
                                    kA_char1=kA_char_cond, kA_char2=kA_char_default,
                                    design=['pr1', 'pr2', 'td_pinch'], offdesign=['zeta1', 'zeta2', 'kA_char'])
        self.comps['pump'].set_attr(eta_s=self.params.pump_eta_s,
                                    eta_s_char=pump_eta_s_char,
                                    design=['eta_s'], offdesign=['eta_s_char'])
        return None

    def set_outer_params(self):
        # 质量流量指定方式
        if self.params.orc_mass_flow:
            self.conns['c00'].set_attr(m=self.params.orc_mass_flow)
        elif self.params.discharge_mass_flow:
            self.conns['c23'].set_attr(m=self.params.discharge_mass_flow)
        else:
            # raise ValueError('Mass flow not of ORC specified')
            pass

        # -------------------- 蓄热侧 --------------------
        self.params.hot_storage_out_temp = self.params.hot_storage_temp
        self.params.cold_storage_in_temp = self.params.cold_storage_temp
        self.conns['c23'].set_attr(T=self.params.hot_storage_out_temp,
                                   p=self.params.hot_storage_out_pressure,
                                   fluid={self.params.heat_storage_fluid_type: 1})
        self.conns['c24'].set_attr(T=self.params.cold_storage_in_temp)
        # -------------------- 冷源侧 --------------------
        self.conns['c31'].set_attr(T=self.params.cold_source_in_temp,
                                   p=self.params.cold_source_in_pressure,
                                   fluid={self.params.cold_source_fluid_type: 1})
        self.conns['c32'].set_attr(T=self.params.cold_source_out_temp)
        return None

    def set_design_params(self):
        """Set the design parameters of the subsystem."""
        if (self.params.orc_temp_evap and self.params.orc_temp_cond
                and self.params.orc_superheat_degree):
            self.comps['evap'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c6'].set_attr(p=None)
            self.comps['cond'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c8'].set_attr(p=None)
        else:
            self.comps['evap'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c6'].set_attr(p=None)
            self.comps['cond'].set_attr(td_pinch=self.params.pinch_point_temp)
            self.conns['c8'].set_attr(p=None)

    def calc_performance(self):
        """Calculate the performance of the subsystem."""
        self.performance['w^(turb)'] = abs(self.comps['turb'].P.val) * self.params.generator_eta / 1e3 / self.conns[
            'c5'].m.val_SI
        self.performance['W^(turb)'] = abs(self.comps['turb'].P.val) * self.params.generator_eta / 1e3
        self.performance['w^(pump)'] = abs(self.comps['pump'].P.val) / self.params.motor_eta / 1e3 / self.conns[
            'c5'].m.val_SI
        self.performance['W^(pump)'] = abs(self.comps['pump'].P.val) / self.params.motor_eta / 1e3
        self.performance['q_(in)^(orc)'] = abs(self.comps['evap'].Q.val) / 1e3 / self.conns['c5'].m.val_SI
        self.performance['Q_(in)^(orc)'] = abs(self.comps['evap'].Q.val) / 1e3
        self.performance['q_(out)^(orc)'] = abs(self.comps['cond'].Q.val) / 1e3 / self.conns['c5'].m.val_SI
        self.performance['Q_(out)^(orc)'] = abs(self.comps['cond'].Q.val) / 1e3
        self.performance['eta_(orc)'] = (self.performance['w^(turb)'] -
                                         self.performance['w^(pump)']) / self.performance['q_(in)^(orc)']
        return None

    def plot_h_p_diagram(self):
        """Plot the h-log(p) diagram of the subsystem."""
        # 有bug
        pass
        result_dict = {}
        result_dict.update({self.comps['evap'].label: self.comps['evap'].get_plotting_data()[2]})
        result_dict.update({self.comps['turb'].label: self.comps['turb'].get_plotting_data()[1]})
        result_dict.update({self.comps['cond'].label: self.comps['cond'].get_plotting_data()[1]})
        result_dict.update({self.comps['pump'].label: self.comps['pump'].get_plotting_data()[1]})

        # 绘图
        diagram = FluidPropertyDiagram(self.params.orc_cycle_fluid_type)
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
        fig.savefig('../results/orc_logph')


if __name__ == "__main__":
    # 参数
    params_path = '../results/params/params_validation_refactored.csv'
    params_test = csv_to_params(params_path)
    orc_test = OrganicRankineCycle('ORC', params_test)
    orc_test.add_outer_conns()
    orc_test.set_outer_params()
    print('orc initialized')
