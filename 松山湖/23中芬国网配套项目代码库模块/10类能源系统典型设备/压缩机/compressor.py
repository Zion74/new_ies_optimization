"""create class of compressors.

Leave one blank line.  The rest of this docstring should contain an
overall description of the module or program.  Optionally, it may also
contain a brief description of exported classes and functions and/or usage
examples.

Typical usage example:

compressor_1 = Compressor()

"""
# import package
from flows import Flow
from devices import Component
from utils import calc_pressure_ratio, set_pressure_ratio


class Compressor(Component):
    """等熵过程计算"""

    def __init__(self, efficiency, pressure_ratio=None, label=None):
        super().__init__(label)
        self.efficiency = efficiency
        self.pressure_ratio = pressure_ratio
        self.label = label
        self.params = {'specific_work': None,
                       'work': None,
                       'fuel exergy': None,
                       'product exergy': None,
                       'exergy destruction': None,
                       'exergy efficiency': None}

    def _process_logic(self, fluid):
        fluid.entropy = self.inlet.entropy
        fluid.pressure = self.inlet.pressure * self.pressure_ratio
        fluid.update_properties()
        self.params['specific_work'] = (fluid.enthalpy - self.inlet.enthalpy) / self.efficiency
        fluid.enthalpy = self.inlet.enthalpy + self.params['specific_work']
        fluid.update_properties()
        self.params['work'] = self.params['specific_work'] * self.inlet.mass_flow
        self.params['fuel exergy'] = self.params['specific_work'] * self.inlet.mass_flow
        self.params['product exergy'] = self.inlet.mass_flow * (fluid.exergy - self.inlet.exergy)
        self.params['exergy destruction'] = self.params['fuel exergy'] - self.params['product exergy']
        self.params['exergy efficiency'] = self.params['product exergy'] / self.params['fuel exergy']


if __name__ == '__main__':
    low_temperature_flow = Flow(mass_flow=1, temperature=367, quality=1)
    high_temperature_flow = Flow(mass_flow=1, temperature=481, quality=0)
    low_temperature_flow.update_properties()
    high_temperature_flow.update_properties()
    print('low_temperature_flow:', low_temperature_flow.__dict__)
    print('high_temperature_flow:', high_temperature_flow.__dict__)
    pressure_ratio_ = calc_pressure_ratio(low_temperature_flow.pressure, high_temperature_flow.pressure, 1)
    print('pressure_ratio_=', pressure_ratio_)
    Compressor = Compressor(efficiency=0.86, pressure_ratio=pressure_ratio_, label='compressor_1')
    Compressor.process(low_temperature_flow)
    print('low_temperature_flow:', low_temperature_flow.__dict__)
    print('Compressor.inlet:', Compressor.inlet.__dict__)
    print('Compressor.outlet:', Compressor.outlet.__dict__)
    print('Compressor.params:', Compressor.params)
    print('Compressor', Compressor.__dict__)
