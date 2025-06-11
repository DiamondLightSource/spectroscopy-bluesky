import enum

from ophyd_async.core import (
    StandardReadable,
)
from ophyd_async.epics.core import epics_signal_r, epics_signal_rw


class GasToInject(enum.Enum):
    ARGON = "argon"
    HELIUM = "helium"
    KRYPTON = "krypton"
    NITROGEN = "nitrogen"


class IonChamberToFill(enum.Enum):
    i0 = "I0"
    i1 = "I1"
    iT = "iT"
    iRef = "iRef"


class VacuumPumpCommands(enum.Enum):
    ON = 0
    OFF = 1


class ValveCommands(enum.Enum):
    RESET = 2
    OPEN = 0
    CLOSE = 1


class PressureMode(enum.Enum):
    HOLD = 0
    PRESSURE_CONTROL = 1


class PressureController(StandardReadable):
    """
    Pressure controller for gas injection system.
    in the old system, it was called MFC1 and MFC2.
    That stood for Mass Flow Controller.
    """

    def __init__(self, prefix: str, name: str = ""):
        with self.add_children_as_readables():
            self.mode = epics_signal_rw(int, prefix + "MODE:RD")
            self.readout = epics_signal_r(float, prefix + "P:RD")
            self.setpoint = epics_signal_rw(float, prefix + "SETPOINT:WR")


# at i20 it's BL20I-EA-GIT-01
class GasInjectionController(StandardReadable):
    def __init__(self, prefix: str, name: str = ""):
        with self.add_children_as_readables():
            self.vacuum_pump = epics_signal_rw(int, prefix + "VACP1:CON")
            self.line_valve = epics_signal_rw(int, prefix + "V5:CON")
            # Gas valves as a dict
            self.gas_valves = {
                GasToInject.KRYPTON: epics_signal_rw(int, prefix + "V1:CON"),
                GasToInject.NITROGEN: epics_signal_rw(int, prefix + "V2:CON"),
                GasToInject.ARGON: epics_signal_rw(int, prefix + "V3:CON"),
                GasToInject.HELIUM: epics_signal_rw(int, prefix + "V4:CON"),
            }
            # Chamber valves as a dict
            self.chambers = {
                IonChamberToFill.i0: epics_signal_rw(int, prefix + "V6:CON"),
                IonChamberToFill.iT: epics_signal_rw(int, prefix + "V7:CON"),
                IonChamberToFill.iRef: epics_signal_rw(int, prefix + "V8:CON"),
                IonChamberToFill.i1: epics_signal_rw(int, prefix + "V9:CON"),
            }
            self.pressure_controller_1 = PressureController(
                prefix + "PCTRL1:", name="pressure_controller_1"
            )
            self.pressure_controller_2 = PressureController(
                prefix + "PCTRL2:", name="pressure_controller_2"
            )

    def get_gas_valve(self, gas: GasToInject):
        return self.gas_valves[gas]

    def get_chamber_valve(self, chamber: IonChamberToFill):
        return self.chambers[chamber]
