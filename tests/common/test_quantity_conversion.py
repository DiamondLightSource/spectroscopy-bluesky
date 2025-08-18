import pytest

from spectroscopy_bluesky.common.quantity_conversion import (
    bragg_angle_to_energy,
    bragg_angle_to_wavelength,
    energy_to_bragg_angle,
    ev_to_wavelength,
    ev_to_wavevector,
    si_311_lattice_spacing,
    wavelength_to_bragg_angle,
    wavelength_to_ev,
    wavevector_to_ev,
)


@pytest.mark.parametrize(
    "energy, expected_wavevector",
    [
        (500, 11.45575017),
        (1000, 16.20087725),
        (1500, 19.84194133),
        (2000, 22.91150034),
        (2500, 25.61583611),
    ],
)
def test_ev_wavevector(energy, expected_wavevector):
    wave = ev_to_wavevector(energy)
    assert wave == pytest.approx(expected_wavevector, 1e-6)
    assert wavevector_to_ev(wave) == pytest.approx(energy, 1e-8)


@pytest.mark.parametrize(
    "energy, expected_wavelength",
    [
        (1000, 12.39841984),
        (2000, 6.19920992),
        (3000, 4.13280661),
        (4000, 3.09960496),
        (5000, 2.47968396),
    ],
)
def test_ev_wavelength(energy, expected_wavelength):
    wave = ev_to_wavelength(energy)
    assert wave == pytest.approx(expected_wavelength, 1e-6)
    assert wavelength_to_ev(wave) == pytest.approx(energy, 1e-8)


@pytest.mark.parametrize(
    "angle, expected_energy",
    [
        (35, 6600.24324372),
        (45, 5353.85050675),
        (55, 4621.54007327),
        (65, 4177.10633510),
        (75, 3919.29058707),
    ],
)
def test_bragg_energy(angle, expected_energy):
    energy = bragg_angle_to_energy(si_311_lattice_spacing, angle)
    assert energy == pytest.approx(expected_energy, 1e-6)
    assert energy_to_bragg_angle(
        si_311_lattice_spacing, energy
        ) == pytest.approx(angle, 1e-8)


@pytest.mark.parametrize(
    "angle, expected_wavelength",
    [
        (35, 1.87847922),
        (45, 2.31579492),
        (55, 2.68274636),
        (65, 2.96818391),
        (75, 3.16343470),
    ],
)
def test_bragg_wavelength(angle, expected_wavelength):
    wavelength = bragg_angle_to_wavelength(si_311_lattice_spacing, angle)
    assert wavelength == pytest.approx(expected_wavelength, 1e-6)
    assert wavelength_to_bragg_angle(
        si_311_lattice_spacing, wavelength
    ) == pytest.approx(angle, 1e-8)
