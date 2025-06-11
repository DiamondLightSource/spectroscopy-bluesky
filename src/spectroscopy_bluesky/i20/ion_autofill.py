import enum

import bluesk.plan_stubs as bps
from dodal.common.types import MsgGenerator

from spectroscopy_bluesky.i20.devices.gas_rig import GasInjectionController

# todo are those parameters? those should be generic
ionchamber2fill = "I0"  # I0, I1, iT, iRef
targetPressureAr = 35  # mbar
targetPressureHe = 1800  # mbar


class GasToInject(enum.Enum):
    ARGON = "argon"
    HELIUM = "helium"
    KRYPTON = "krypton"
    NITROGEN = "nitrogen"


class IonChamberToFill(enum.Enum):
    I0 = "I0"
    I1 = "I1"
    iT = "iT"
    iRef = "iRef"


def get_gas_valve(gas_injector, gas_to_inject: GasToInject):
    gas_map = {
        GasToInject.ARGON: gas_injector.ar_valve,
        GasToInject.HELIUM: gas_injector.he_valve,
        GasToInject.KRYPTON: gas_injector.kr_valve,
        GasToInject.NITROGEN: gas_injector.n2_valve,
    }
    return gas_map[gas_to_inject]


ionchamber_purge_time = 20.00  # 30
ionchamber_leak_wait_time = 10.0  # 10
injection_equilibration_wait_time = 20
helium_equilibration_wait_time = 10.0


def get_chamber_valve(gas_injector, ion_chamber: IonChamberToFill):
    # Map chamber to the correct valve only
    chamber_valve_map = {
        IonChamberToFill.I0: gas_injector.i0_valve,
        IonChamberToFill.I1: gas_injector.i1_valve,
        IonChamberToFill.iT: gas_injector.it_valve,
        IonChamberToFill.iRef: gas_injector.iref_valve,
    }
    return chamber_valve_map[ion_chamber]


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


def ion_autofill(
    gas_injector: GasInjectionController,
    target_pressure_mbar: float,
    ion_chamber: IonChamberToFill = IonChamberToFill.I0,
    gas_to_inject: GasToInject = GasToInject.ARGON,
) -> MsgGenerator:
    """
    NOTE scientifically we do small portion of the heavy gas to measure flux
    we use the light gas (Helium) to make sure that the pressure is positive so that
    we do not get air leak into the ion chamber.
    """
    chamber_valve = get_chamber_valve(gas_injector, ion_chamber)
    gas_valve = get_gas_valve(gas_injector, gas_to_inject)
    chamber_pressure = (
        gas_injector.pressure_controller_2
    )  # Always use controller 2 for chamber valves

    # todo when to run this?
    def purge_line(valve, pressure: float) -> MsgGenerator:
        # turn on the the vacuum pump - reset, open
        yield from bps.mv(gas_injector.vacuum_pump, VacuumPumpCommands.ON)

        # open valve line valve
        yield from bps.mv(gas_injector.line_valve, ValveCommands.RESET)
        yield from bps.mv(gas_injector.line_valve, ValveCommands.OPEN)
        # open valve
        line_pressure = (
            yield from bps.rd(gas_injector.pressure_controller_1.readout)
        )["value"]
        LIMIT_PRESSURE = 8.5  # mbar
        print("purging the gas-supply line...")
        while line_pressure > LIMIT_PRESSURE:
            yield from bps.sleep(1)
            line_pressure = (
                yield from bps.rd(gas_injector.pressure_controller_1.readout)
            )["value"]
        yield from bps.mv(gas_injector.line_valve, ValveCommands.CLOSE)
        yield from bps.mv(gas_injector.vacuum_pump, VacuumPumpCommands.OFF)

    def inject_gas(target_pressure) -> MsgGenerator:
        yield from bps.mv(chamber_pressure.setpoint, target_pressure)
        yield from bps.mv(gas_valve, ValveCommands.RESET)
        yield from bps.mv(gas_valve, ValveCommands.OPEN)
        yield from bps.mv(chamber_pressure.mode, PressureMode.PRESSURE_CONTROL)
        yield from bps.sleep(injection_equilibration_wait_time)
        yield from bps.mv(chamber_valve, ValveCommands.CLOSE)
        yield from bps.mv(chamber_pressure.mode, PressureMode.HOLD)
        yield from bps.mv(gas_valve, ValveCommands.CLOSE)

    def purge_chamber() -> MsgGenerator:
        yield from bps.mv(gas_injector.vacuum_pump, VacuumPumpCommands.ON)
        yield from bps.mv(gas_injector.line_valve, ValveCommands.RESET)
        yield from bps.mv(gas_injector.line_valve, ValveCommands.OPEN)
        yield from bps.mv(chamber_valve, ValveCommands.RESET)
        yield from bps.mv(chamber_valve, ValveCommands.OPEN)
        base_pressure = (yield from bps.rd(chamber_pressure.readout))["value"]
        yield from bps.mv(chamber_valve, ValveCommands.CLOSE)
        # wait for leak check
        yield from bps.sleep(ionchamber_leak_wait_time)
        check_pressure = (yield from bps.rd(chamber_pressure.readout))["value"]
        if check_pressure - base_pressure > 3:
            print(f"WARNING, suspected leak in {ion_chamber}, stopping here!!!")
        yield from bps.mv(chamber_valve, ValveCommands.CLOSE)
        yield from bps.mv(gas_injector.line_valve, ValveCommands.CLOSE)
        yield from bps.mv(gas_injector.vacuum_pump, VacuumPumpCommands.OFF)

    # Example usage in your plan:
    yield from purge_chamber()
    yield from inject_gas(target_pressure_mbar)
