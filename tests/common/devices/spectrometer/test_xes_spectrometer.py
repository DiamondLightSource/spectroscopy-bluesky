from unittest.mock import AsyncMock

import pytest
from ophyd_async.core import init_devices
from ophyd_async.testing import assert_reading, partial_reading

from spectroscopy_bluesky.common.devices.spectrometer import (
    AnalyserDevice,
    DetectorDevice,
    XesSpectrometerBragg,
    XesSpectrometerEnergy,
)
from spectroscopy_bluesky.common.quantity_conversion import (
    bragg_angle_to_energy,
    energy_to_bragg_angle,
    lattice_parameter_si,
    si_111_lattice_spacing,
)


@pytest.fixture
async def spectrometer_bragg() -> XesSpectrometerBragg:
    async with init_devices(mock=True):
        m1 = AnalyserDevice("minus1", -1)
        centre = AnalyserDevice("centre", 0)
        p1 = AnalyserDevice("plus1", 1)
        detector = DetectorDevice("det")

    spectrometer_bragg = XesSpectrometerBragg(
        1000.0, [m1, centre, p1], detector, name="spectrometer"
    )
    spectrometer_bragg.trajectory_step_size = 1.0
    return spectrometer_bragg


@pytest.fixture
async def spectrometer_energy(
    spectrometer_bragg: XesSpectrometerBragg,
) -> XesSpectrometerEnergy:
    return XesSpectrometerEnergy(
        spectrometer_bragg,
        crystal_cut=[1, 1, 1],
        lattice_parameter=lattice_parameter_si,
        name="spectrometer_energy",
    )


def out_of_range_angles(spectrometer_bragg: XesSpectrometerBragg) -> list[float]:
    return [
        spectrometer_bragg.bragg_lower_limit - 0.5,
        spectrometer_bragg.bragg_upper_limit + 0.5,
    ]


@pytest.mark.parametrize("bragg_angle", [65, 70, 75, 80, 85])
async def test_spectrometer_bragg_positions(
    spectrometer_bragg: XesSpectrometerBragg, bragg_angle: float
):
    await spectrometer_bragg.set(bragg_angle)

    await assert_reading(
        spectrometer_bragg,
        {spectrometer_bragg.name + "-bragg_angle_rbv": partial_reading(bragg_angle)},
    )

    # Collect the motor rbv positions for each analyser
    rbv_analyser_positions = {
        c.horizontal_index: await c.get_rbv_positions()
        for c in spectrometer_bragg.analyser_crystals
    }

    # Calculate expected positions and check rbv positions match
    xes_calculator = spectrometer_bragg.xes_calculator
    for index, positions in rbv_analyser_positions.items():
        calculated_positions = xes_calculator.calculate_analyser_position(
            bragg_angle, index
        )
        assert positions == pytest.approx(calculated_positions, 1e-6)

    # Check the detector position
    rbv_detector_positions = (
        await spectrometer_bragg.detector_device.get_rbv_positions()
    )
    assert rbv_detector_positions == pytest.approx(
        xes_calculator.calculate_detector_position(bragg_angle)
    )


@pytest.mark.parametrize("energy", [2000, 2050, 2100, 2150, 2200, 2250])
async def test_spectrometer_energy_positions(
    spectrometer_energy: XesSpectrometerEnergy, energy: float
):
    await spectrometer_energy.set(energy)
    expected_bragg = energy_to_bragg_angle(si_111_lattice_spacing, energy)

    await assert_reading(
        spectrometer_energy,
        {
            spectrometer_energy.name + "-crystal_cut": partial_reading([1, 1, 1]),
            spectrometer_energy.name + "-xes_energy": partial_reading(energy),
            spectrometer_energy.name + "-xes_bragg": partial_reading(expected_bragg),
        },
    )


async def test_bragg_out_of_range_raises_exception(
    spectrometer_bragg: XesSpectrometerBragg,
):
    angles = out_of_range_angles(spectrometer_bragg)
    for angle in angles:
        with pytest.raises(ValueError):
            await spectrometer_bragg.set(angle)


async def test_energy_out_of_range_raises_exception(
    spectrometer_energy: XesSpectrometerEnergy, spectrometer_bragg: XesSpectrometerBragg
):
    angles = out_of_range_angles(spectrometer_bragg)
    energies = [bragg_angle_to_energy(si_111_lattice_spacing, a) for a in angles]
    for energy in energies:
        with pytest.raises(ValueError):
            await spectrometer_energy.set(energy)


async def test_bad_energy_raises_exception(
    spectrometer_energy: XesSpectrometerEnergy, spectrometer_bragg: XesSpectrometerBragg
):
    bad_energies = [-10, 0, 10]
    for energy in bad_energies:
        with pytest.raises(ValueError):
            await spectrometer_energy.set(energy)


async def check_if_devices_move(
    spectrometer_bragg: XesSpectrometerBragg,
    bragg_angle: float,
    bragg_step: float,
    move_happens: bool,
):

    # move into position
    await spectrometer_bragg.set(bragg_angle)

    analyser_mocks: list[AsyncMock] = []

    # mock the 'set' mothods on analyser and detector devices
    for c in spectrometer_bragg.analyser_crystals:
        c.set = AsyncMock()
        analyser_mocks.append(c.set)

    spectrometer_bragg.detector_device.set = AsyncMock()

    # move to new position
    await spectrometer_bragg.set(bragg_angle + bragg_step)

    # check to see that 'set' methods have been called expected number of times
    for m in analyser_mocks:
        assert (len(m.mock_calls) > 0) == move_happens

    assert (len(spectrometer_bragg.detector_device.set.mock_calls) > 0) == move_happens


@pytest.mark.parametrize("bragg_angle", [65, 70, 65, 80, 85])
async def test_no_bragg_change_moves_nothing(
    spectrometer_bragg: XesSpectrometerBragg, bragg_angle: float
):
    await check_if_devices_move(spectrometer_bragg, bragg_angle, 0, False)


@pytest.mark.parametrize("bragg_angle", [65, 70, 65, 80, 85])
async def test_bragg_change_move_tolerance(
    spectrometer_bragg: XesSpectrometerBragg, bragg_angle: float
):
    spectrometer_bragg.analyser_move_tolerance = [0.1, 0.1, 0.1, 0.1]
    spectrometer_bragg.detector_move_tolerance = [0.1, 0.1, 0.1]

    # Nothing should move
    await check_if_devices_move(spectrometer_bragg, bragg_angle, 0, False)

    # Small change, within motor move tolerance - should move nothing
    await check_if_devices_move(spectrometer_bragg, bragg_angle + 0.001, 0, False)

    # Larger change, exeeding motor tolerance - analysers and detector should all move
    await check_if_devices_move(spectrometer_bragg, bragg_angle + 1.0, 0, True)
