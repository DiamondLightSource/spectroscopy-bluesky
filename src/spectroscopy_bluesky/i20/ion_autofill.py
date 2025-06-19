from asyncio import gather

from dodal.common.types import MsgGenerator
from dodal.i20.devices.gas_rig import (
    GasInjectionController,
    GasToInject,
    IonChamberToFill,
)


def purge_line(gas_injector: GasInjectionController) -> MsgGenerator:
    yield from gas_injector.purge_line()


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
    Parameters:
    - gas_injector: GasInjectionController instance
    - target_pressure_mbar: Target pressure in mbar to set in the ion chamber
    - ion_chamber: IonChamberToFill enum value indicating which ion chamber to fill
    - gas_to_inject: GasToInject enum value indicating which gas to inject
    Returns:
    - A generator that yields messages for the bluesky plan
    """
    yield from purge_line(gas_injector)
    gather(gas_injector.purge_chamber(ion_chamber))
    gather(
        gas_injector.inject_gas(
            target_pressure_mbar,
            ion_chamber,
            gas_to_inject,
        )
    )
