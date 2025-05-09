import os
from enum import Enum

os.environ["EPICS_CA_SERVER_PORT"] = "6064"

from ophyd import Component as Cpt
from ophyd import EpicsSignal, EpicsSignalRO
from ophyd.pv_positioner import PVPositioner


class EpicsMotorPositioner(PVPositioner):
    """PVPositioner implementation that uses
    a limited subset of the PVs available in Epics motor record.
    Uses the .VAL record to set the position, .RBV for readback, .DMOV
    for the 'busy' status and .STOP to stop the motor.

    """

    setpoint = Cpt(EpicsSignal, ".VAL")
    readback = Cpt(EpicsSignalRO, ".RBV")
    done = Cpt(EpicsSignalRO, ".DMOV")
    stop_signal = Cpt(EpicsSignal, ".STOP")
    stop_value = 1
    done_value = 1


class FilterAValues(Enum):
    """Maps from a short usable name to the string name in EPICS"""

    Al_2MM = "2 mm Al"
    Al_1_5MM = "1.5 mm Al"
    Al_1_25MM = "1.25 mm Al"
    Al_0_8MM = "0.8 mm Al"
    Al_0_3MM = "0.3 mm Al"
    Al_0_55MM = "0.55 mm Al"
    Al_0_5MM = "0.5 mm Al"
    Al_0_25MM = "0.25 mm Al"
    Al_0_15MM = "0.15 mm Al"
    Al_Gap = "Gap"
    Al_0_025MM = "0.025 mm Al"
    Al_0_1MM = "0.1 mm Al"

    def __str__(self):
        return self.name.capitalize()


values_dict_micrometers: dict[FilterAValues, int] = {
    FilterAValues.Al_Gap: 000,
    FilterAValues.Al_0_025MM: 25,
    FilterAValues.Al_0_1MM: 100,
    FilterAValues.Al_0_15MM: 150,
    FilterAValues.Al_0_25MM: 250,
    FilterAValues.Al_0_3MM: 300,
    FilterAValues.Al_0_5MM: 500,
    FilterAValues.Al_0_55MM: 550,
    FilterAValues.Al_0_8MM: 800,
    FilterAValues.Al_1_25MM: 1250,
    FilterAValues.Al_1_5MM: 1500,
    FilterAValues.Al_2MM: 2000,
}
default_starting_thickness = FilterAValues.Al_0_15MM
as_list = list(values_dict_micrometers.keys())


def increase_thickness(current_thickness: FilterAValues) -> FilterAValues:
    """
    to use when the diode saturation becomes a hindrance to the plan
    :param current_thickness:
    :return:
    """
    index = as_list.index(current_thickness)
    new_value = as_list[index + 1]
    return new_value


class D7Positioner(PVPositioner):
    setpoint = Cpt(EpicsSignal, ":SELECT")
    readback = Cpt(EpicsSignalRO, ":SELECT")
    done = Cpt(EpicsSignalRO, ":DMOV")
    stop_signal = Cpt(EpicsSignal, ":STOP.PROC")
    done_value = 1
    stop_value = 1


pv_prefix = "ws416-MO-SIM-01:M2"
# pv_prefix = "SR18I-MO-SERVC-01:BLGAPMTR"

d7FilterPositioner = D7Positioner("BL18I-DI-PHDGN-07:A:MP", name="d7FilterPositioner")
d7DiodePositioner = D7Positioner("BL18I-DI-PHDGN-07:B:MP", name="d7DiodePositioner")

# epics_motor = EpicsMotor(pv_prefix, name="epics_motor")

# bec = BestEffortCallback()
# RE = RunEngine()
# RE.subscribe(bec)

# RE(scan([simple_positioner], simple_positioner, 1, 10, 10))
# RE(scan([epics_motor], epics_motor, 1, 10, 10))
