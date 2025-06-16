from unittest.mock import MagicMock

import pytest

from spectroscopy_bluesky.i20.devices.gas_rig import GasInjectionController
from spectroscopy_bluesky.i20.ion_autofill import (
    GasToInject,
    get_gas_valve,
)

test_gas_injector = MagicMock(spec=GasInjectionController)


@pytest.fixture
def gas_injector():
    """Fixture to provide a mock GasInjectionController."""
    return test_gas_injector


# todo finish up the test
def test_get_gas_valve(gas_injector):
    """Test the get_gas_valve function."""
    # Test for each gas type
    for gas in GasToInject:
        valve = get_gas_valve(gas_injector, gas)
        assert valve is gas_injector.gas_valves[gas], (
            f"Failed for {gas.value}"
        )

    # Test with an invalid gas type
    with pytest.raises(KeyError):
        get_gas_valve(gas_injector, "invalid_gas")  # This should raise an error
