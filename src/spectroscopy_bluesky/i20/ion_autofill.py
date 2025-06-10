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


def get_gas_valve(gir, gas_to_inject: GasToInject):
    gas_map = {
        GasToInject.ARGON: gir.ar_valve,
        GasToInject.HELIUM: gir.he_valve,
        GasToInject.KRYPTON: gir.kr_valve,
        GasToInject.NITROGEN: gir.n2_valve,
    }
    return gas_map[gas_to_inject]


ionchamber_purge_time = 20.00  # 30
ionchamber_leak_wait_time = 10.0  # 10
injection_equilibration_wait_time = 20
helium_equilibration_wait_time = 10.0


def get_chamber_valve(gir, ion_chamber: IonChamberToFill):
    # Map chamber to the correct valve only
    chamber_valve_map = {
        IonChamberToFill.I0: gir.i0_valve,
        IonChamberToFill.I1: gir.i1_valve,
        IonChamberToFill.iT: gir.it_valve,
        IonChamberToFill.iRef: gir.iref_valve,
    }
    return chamber_valve_map[ion_chamber]


def ion_autofill(
    gir: GasInjectionController,
    target_pressure_mbar: float,
    ion_chamber: IonChamberToFill = IonChamberToFill.I0,
    gas_to_inject: GasToInject = GasToInject.ARGON,
) -> MsgGenerator:
    """
    NOTE scientifically we do small portion of the heavy gas to measure flux
    we use the light gas (Helium) to make sure that the pressure is positive so that
    we do not get air leak into the ion chamber.
    """
    chamber_valve = get_chamber_valve(gir, ion_chamber)
    gas_valve = get_gas_valve(gir, gas_to_inject)
    chamber_pressure = (
        gir.pressure_controller_2
    )  # Always use controller 2 for chamber valves

    # todo when to run this?
    def purge_line(valve, pressure: float) -> MsgGenerator:
        # turn on the the vacuum pump - reset, open
        yield from bps.mv(gir.vacuum_pump, 0)

        # open valve line valve
        yield from bps.mv(gir.line_valve, 2)  # reset
        yield from bps.mv(gir.line_valve, 0)
        # open valve
        line_pressure = (yield from bps.read(gir.pressure_controller_1.readout))[
            "value"
        ]
        LIMIT_PRESSURE = 8.5  # mbar
        print("purging the gas-supply line...")
        while line_pressure > LIMIT_PRESSURE:
            yield from bps.sleep(1)
            line_pressure = (yield from bps.read(gir.pressure_controller_1.readout))[
                "value"
            ]
        # close line valve
        yield from bps.mv(gir.line_valve, 1)
        # turn off the vacuum pump
        yield from bps.mv(gir.vacuum_pump, 1)

    def inject_gas(target_pressure) -> MsgGenerator:
        # move mode to pressure control
        yield from bps.mv(chamber_pressure.setpoint, target_pressure)
        # reset and open gas valve
        yield from bps.mv(gas_valve, 2)
        yield from bps.mv(gas_valve, 0)
        # set mode to pressure control
        yield from bps.mv(chamber_pressure.mode, 1)
        # wait for pressure to equilibrate
        yield from bps.sleep(injection_equilibration_wait_time)
        # close chamber valve
        yield from bps.mv(chamber_valve, 1)
        # set mode back to hold
        yield from bps.mv(chamber_pressure.mode, 0)
        # close gas valve
        yield from bps.mv(gas_valve, 1)

    def purge_chamber() -> MsgGenerator:
        # turn on the vacuum pump
        yield from bps.mv(gir.vacuum_pump, 0)
        # reset and open line valve
        yield from bps.mv(gir.line_valve, 2)
        yield from bps.mv(gir.line_valve, 0)
        # reset and open chamber valve
        yield from bps.mv(chamber_valve, 2)
        yield from bps.mv(chamber_valve, 0)
        base_pressure = (yield from bps.read(chamber_pressure.readout))["value"]
        # close chamber valve
        yield from bps.mv(chamber_valve, 1)
        # wait for leak check
        yield from bps.sleep(ionchamber_leak_wait_time)
        check_pressure = (yield from bps.read(chamber_pressure.readout))["value"]
        if check_pressure - base_pressure > 3:
            print(f"WARNING, suspected leak in {ion_chamber}, stopping here!!!")
        # close chamber valve
        yield from bps.mv(chamber_valve, 1)
        # close line valve
        yield from bps.mv(gir.line_valve, 1)
        # turn off the vacuum pump
        yield from bps.mv(gir.vacuum_pump, 1)

    # Example usage in your plan:
    yield from purge_chamber()
    yield from inject_gas(target_pressure_mbar)
