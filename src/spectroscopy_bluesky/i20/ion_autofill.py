import bluesky.plan_stubs as bps
from dodal.common.types import MsgGenerator
from dodal.log import LOGGER

from spectroscopy_bluesky.i20.devices.gas_rig import (
    GasInjectionController,
    GasToInject,
    IonChamberToFill,
    PressureMode,
    VacuumPumpCommands,
    ValveCommands,
)

ionchamber_leak_wait_time = 10.0
injection_equilibration_wait_time = 20


def ion_autofill(
    gas_injector: GasInjectionController,
    target_pressure_mbar: float,
    ion_chamber: IonChamberToFill = IonChamberToFill.i0,
    gas_to_inject: GasToInject = GasToInject.ARGON,
) -> MsgGenerator:
    """
    Usual usage:
    targetPressureAr = 35
    targetPressureHe = 1800
    NOTE scientifically we do small portion of the heavy gas to measure flux
    we use the light gas (Helium) to make sure that the pressure is positive so that
    we do not get air leak into the ion chamber.
    Parameters:
    - gas_injector: GasInjectionController instance
    - target_pressure_mbar: Target pressure in mbar to set in the ion chamber
    - ion_chamber: IonChamberToFill enum value indicating which ion chamber to fill
    - gas_to_inject: GasToInject enum value indicating which gas to inject
    Returns:
    - A generator that yields messages for the bluesky plan
    """
    chamber_valve = gas_injector.get_chamber_valve(ion_chamber)
    gas_valve = gas_injector.get_gas_valve(gas_to_inject)
    chamber_pressure = gas_injector.pressure_controller_2

    # todo when to run this?
    def purge_line(valve, pressure: float) -> MsgGenerator:
        # turn on the the vacuum pump - reset, open
        yield from bps.mv(gas_injector.vacuum_pump, VacuumPumpCommands.ON)

        # open valve line valve
        yield from bps.mv(gas_injector.line_valve, ValveCommands.RESET)
        yield from bps.mv(gas_injector.line_valve, ValveCommands.OPEN)
        # open valve
        # todo move this into the device
        # from ophyd_async.core import observe_value, observe_signals_value
        # line_pressure_iterator = observe_value(
        #     gas_injector.pressure_controller_1.readout
        # )
        # value = await anext(line_pressure_iterator)
        line_pressure = (yield from bps.rd(gas_injector.pressure_controller_1.readout))[
            "value"
        ]
        LIMIT_PRESSURE = 8.5  # mbar
        LOGGER.warn("purging the gas-supply line...")
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
            LOGGER.warn(f"WARNING, suspected leak in {ion_chamber}, stopping here!!!")
        yield from bps.mv(chamber_valve, ValveCommands.CLOSE)
        yield from bps.mv(gas_injector.line_valve, ValveCommands.CLOSE)
        yield from bps.mv(gas_injector.vacuum_pump, VacuumPumpCommands.OFF)

    # Example usage in your plan:
    yield from purge_chamber()
    yield from inject_gas(target_pressure_mbar)
