from ophyd_async.core import (
    StandardReadable,
)
from ophyd_async.epics.core import epics_signal_r, epics_signal_rw


# todo if just 1 channel do we need helper methods?
class VacuumPump(StandardReadable):
    def __init__(self, prefix: str, name: str = ""):
        with self.add_children_as_readables():
            self.vacuum_pump = epics_signal_rw(int, prefix + "VACP1:CON")


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
            # todo possibly extract the pressure detection into a device with separate mode, reaodout and setpoint
            self.pressure_1_mode = epics_signal_r(int, prefix + "PCTRL1:MODE:RD")
            self.pressure_1_readout = epics_signal_r(flaot, prefix + "PCTRL1:P:RD")
            self.pressure_2_mode = epics_signal_r(int, prefix + "PCTRL2:MODE:RD")
            self.pressure_2_readout = epics_signal_r(float, prefix + "P2")
            self.pressure_1_setpoint = epics_signal_rw(
                float, prefix + "PCTRL1:SETPOINT:WR"
            )
            self.pressure_2_setpoint = epics_signal_rw(
                float, prefix + "PCTRL2:SETPOINT:WR"
            )
