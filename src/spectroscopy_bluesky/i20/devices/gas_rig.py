from ophyd_async.core import (
    StandardReadable,
)
from ophyd_async.epics.core import epics_signal_r, epics_signal_rw


class PressureController(StandardReadable):
    def __init__(self, prefix: str, name: str = ""):
        with self.add_children_as_readables():
            self.mode = epics_signal_rw(int, prefix + "MODE:RD")
            self.readout = epics_signal_r(float, prefix + "P:RD")
            self.setpoint = epics_signal_rw(float, prefix + "SETPOINT:WR")


# at i20 it's BL20I-EA-GIT-01
# todo dicuss how to compose devices really
class GasInjectionController(StandardReadable):
    def __init__(self, prefix: str, name: str = ""):
        with self.add_children_as_readables():
            self.vacuum_pump = epics_signal_rw(
                int, prefix + "VACP1:CON"
            )  # 0 to on, 1 to off
            self.line_valve = epics_signal_rw(int, prefix + "V5:CON")
            self.i0_valve = epics_signal_rw(int, prefix + "V6:CON")
            self.ar_valve = epics_signal_rw(int, prefix + "V3:CON")
            self.kr_valve = epics_signal_rw(int, prefix + "V1:CON")
            self.n2_valve = epics_signal_rw(int, prefix + "V2:CON")
            self.pressure_controller_1 = PressureController(
                prefix + "PCTRL1:", name="pressure_controller_1"
            )
            self.pressure_controller_2 = PressureController(
                prefix + "PCTRL2:", name="pressure_controller_2"
            )
