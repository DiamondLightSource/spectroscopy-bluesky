"""
Collection of functions and constants to help perform conversion between quantities
in various different units.
e.g. convert energy to wavelength, energy to wavevector, Bragg angle to wavelength etc
"""
import math
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from scipy.constants import (
    Planck,
    angstrom,
    electron_mass,
    elementary_charge,
    hbar,
    physical_constants,
    speed_of_light,
)

ndarray_or_number: TypeAlias = NDArray | float | int
""" type representing an int, a float or a numpy array """

lattice_parameter_si: float = physical_constants["lattice parameter of silicon"][0]
""" Lattice parameter of Si (at temperature of 22.5C) """

const_ev_to_angstrom: float = Planck * speed_of_light / (angstrom * elementary_charge)
""" Conversion factor from energy in eV to wavelength in Angstroms"""


def ev_to_wavelength(energy_ev: ndarray_or_number) -> float:
    """Convert from energy (eV) to wavelength (Angstroms)

    Args:
        energy_ev (NDAarray|float|int):

    Returns:
        NDAarray|float|int: wavelength (Angstroms)
    """
    return const_ev_to_angstrom / energy_ev


def wavelength_to_ev(wavelength_angstrom: ndarray_or_number) -> ndarray_or_number:
    """Convert from wavelength (Angstroms) to energy (eV)

    Args:
        wavelength_angstrom (NDAarray|float|int):

    Returns:
        NDAarray|float|int: energy (eV)
    """
    return const_ev_to_angstrom / wavelength_angstrom


def crystal_spacing(lattice_parameter: float, miller_indices: list[int]) -> float:
    """Calculate crystal latiice spacing from lattice parameter and Miller indices
    using : lattice_spacing = lattice_parameter/sqrt(h*h + k*k + l*l)

    Args:
        lattice_parameter (float): crystal lattice parameter
        indices (list[int]): Miller indices (h,k,l)

    Raises:
        Exception: if number of Miller indices != 3

    Returns:
        float: crystal lattice spacing
    """
    if len(miller_indices) != 3:
        raise Exception(
            "Need 3 values for the Miller indices to calculate lattice spacing!"
        )

    denom = float(sum([i * i for i in miller_indices]))
    return lattice_parameter / math.sqrt(denom)


def bragg_angle_to_wavelength(
    lattice_spacing: float, angle_deg: ndarray_or_number
) -> NDArray :
    """Convert from Bragg angle (degrees) to wavelength (Angstroms)

    Args:
        lattice_spacing (float): crystal lattice spacing (metres)
        angle_deg (NDArray|float|int): Bragg angle (degrees)

    Returns:
        NDArray|float|int: wavelength (Angstroms)
    """
    return 2 * lattice_spacing * np.sin(np.radians(angle_deg)) / angstrom


def energy_to_bragg_angle(
    lattice_spacing: float, energy_ev: ndarray_or_number, return_radians=False
) -> NDArray:
    """Convert photon energy (eV) to Bragg angle
    (using :func:`ev_to_wavelength` and :func:`wavelength_to_bragg_angle`)

    Args:
        lattice_spacing (float): crystal lattice spacing (metres)
        energy_ev (ndarray_or_number): photon energy (eV)
        return_radians (bool, optional): Defaults to False.

    Returns:
        NDArray: _description_
    """
    wavelength = ev_to_wavelength(energy_ev)
    return wavelength_to_bragg_angle(lattice_spacing, wavelength, return_radians=False)

def bragg_angle_to_energy(
    lattice_spacing: float, bragg_angle_degrees: ndarray_or_number
) -> NDArray:
    """Convert Bragg angle (degrees) to energy (ev)

    Args:
        lattice_spacing (float): crystal lattice spacing (metres)
        bragg_angle_degrees (ndarray_or_number): _description_

    Returns:
        NDArray: _description_
    """
    wavelength = bragg_angle_to_wavelength(lattice_spacing, bragg_angle_degrees)
    return wavelength_to_ev(wavelength)


def wavelength_to_bragg_angle(
    lattice_spacing: float, wavelength_angstroms: ndarray_or_number, return_radians=False
) -> ndarray_or_number:
    """Convert wavelength (Angstroms) to Bragg angle (radians, degrees)

    Args:
        lattice_spacing (float): crystal lattice spacing (metres)
        wavelength_angstroms (NDArray|float|int): wavelength (Angstroms)
        return_radians (bool, optional): Calculate angles in radians if set to true.
            (Default == True).

    Raises:
        Exception: if wavelength > 2*lattice_spacing

    Returns:
        NDArray|float|int: Bragg angle (radians or degrees, depending on return_radians)
    """
    val = wavelength_angstroms * angstrom / (2 * lattice_spacing)
    if val > 1:
        raise Exception(
            f"Wavelength {wavelength_angstroms} Angstroms is too large for "
            "lattice spacing {lattice_spacing/angstrom} Angstroms!"
        )

    theta = np.asin(val)
    return theta if return_radians else np.degrees(theta)


def wavevector_to_ev(wavevec_inverse_angstrom: ndarray_or_number) -> ndarray_or_number:
    """Convert from wavevector (inverse Angstroms) to photon energy (eV) using
    E = (hbar*k)**2 / 2m

    Args:
        wavevec_inverse_angstrom (NDarray|float|int): wavevector (inverse Angstroms)

    Returns:
        NDAarray|float|int: photon energy (eV)
    """
    return ((hbar * wavevec_inverse_angstrom / angstrom) ** 2) / (
        2 * electron_mass * elementary_charge
    )


def ev_to_wavevector(energy_ev: ndarray_or_number) -> ndarray_or_number:
    """Convert from photon energy (eV) to wavevector (inverse Angstroms) using
    E = (hbar*k)**2 / 2m  -> k = sqrt(2mE/hbar)

    Args:
        energy_ev (NDAarray|float|int): photon energy (eV)

    Returns:
        NDAarray|float|int: inverse wavelength (inverse Angstroms)
    """
    wave_vec_si = np.sqrt(2.0 * electron_mass * elementary_charge * energy_ev) / hbar

    return wave_vec_si * angstrom


si_111_lattice_spacing = crystal_spacing(lattice_parameter_si, [1, 1, 1])
si_311_lattice_spacing = crystal_spacing(lattice_parameter_si, [3, 1, 1])
