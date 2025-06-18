from unittest.mock import MagicMock

import pytest
from bluesky import RunEngine

from spectroscopy_bluesky.i20.devices.gas_rig import (
    GasInjectionController,
    IonChamberToFill,
)
from spectroscopy_bluesky.i20.ion_autofill import (
    GasToInject,
    ion_autofill,
)


@pytest.fixture
def gas_injector():
    """Fixture to provide a mock GasInjectionController."""
    return MagicMock(spec=GasInjectionController)


def test_get_gas_valve(gas_injector: GasInjectionController, RE: RunEngine):
    """Test the get_gas_valve function."""
    gas_injector.purge_chamber = MagicMock()
    gas_injector.chambers = {}
    # gas_injector.gas_valves = {GasToInject.ARGON: MagicMock()}
    gas_injector.gas_valves = {}
    gas_injector.gas_valves[GasToInject.ARGON] = MagicMock()
    gas_injector.chambers[IonChamberToFill.i0] = MagicMock()
    gas_injector.get_gas_valve = MagicMock(
        return_value=gas_injector.gas_valves[GasToInject.ARGON]
    )
    gas_valve = gas_injector.get_gas_valve(GasToInject.ARGON)
    assert gas_valve == gas_injector.gas_valves[GasToInject.ARGON]
    # call the plan

    RE(
        ion_autofill(
            gas_injector,
            35.0,
            IonChamberToFill.i0,
            GasToInject.ARGON,
        )
    )
    gas_injector.inject_gas = MagicMock()
    gas_injector.purge_chamber.assert_called_once()
    gas_injector.purge_chamber.assert_called_once_with(IonChamberToFill.i0)
    gas_injector.inject_gas.assert_called_once_with(
        35.0, IonChamberToFill.i0, GasToInject.ARGON
    )
