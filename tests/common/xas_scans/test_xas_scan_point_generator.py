import math

from numpy.typing import NDArray

from spectroscopy_bluesky.common.xas_scans import (
    XasScanParameters,
    XasScanPointGenerator,
)


def create_base_params():
    params = XasScanParameters("Mn", "K")
    params.initialEnergy = 100
    params.a = 110
    params.b = 115
    params.c = 120
    params.finalEnergy = 130

    params.preEdgeStep = 0.7
    params.edgeStep = 0.4
    params.exafsStep = 4

    params.preEdgeTime = 1
    params.edgeTime = 5.0
    params.exafsTime = 0.5

    params.exafsTimeType = "Constant time"
    params.exafsStepType = "E"

    params.adjust_a_energy()

    return params


def calculate_grid(xas_params: XasScanParameters) -> tuple[NDArray, NDArray]:
    gen = XasScanPointGenerator(xas_params)
    grid = gen.calculate_energy_time_grid()
    return grid[:, 0], grid[:, 1]


def assert_approx_equals(val, expected, diff=1e-4):
    assert math.fabs(val - expected) < diff


def assert_increasing(energies: NDArray):
    for i in range(energies.size - 1):
        assert energies[i] < energies[i + 1]


def test_energies_const_e_exafs():
    params = create_base_params()
    energies, _ = calculate_grid(params)

    print(energies)
    assert len(energies) == 41
    assert_increasing(energies)
    assert_approx_equals(energies[10], 107.0)
    assert_approx_equals(energies[20], 113.2656)
    assert_approx_equals(energies[24], 115.0)

    params.preEdgeStep = 2
    params.edgeStep = 1
    params.exafsStep = 5
    params.adjust_a_energy()

    energies, _ = calculate_grid(params)
    print(energies)
    assert len(energies) == 17
    assert_increasing(energies)
    assert_approx_equals(energies[5], 109.848)
    assert_approx_equals(energies[15], 125.0)


def test_energies_const_k_exafs():
    params = create_base_params()
    params.exafsStepType = "k"
    params.exafsStep = 0.1
    params.edgeEnergy = 117

    energies, _ = calculate_grid(params)
    print(energies)

    assert len(energies) == 50
    assert_increasing(energies)
    assert_approx_equals(energies[37], 120.0)
    assert_approx_equals(energies[47], 127.896907)


def test_time_varying_exafs():
    params = create_base_params()
    params.exafsTimeType = "variable time"
    params.exafsFromTime = 0.1
    params.exafsToTime = 1.0
    params.kWeighting = 1.0
    energies, times = calculate_grid(params)

    assert energies.size == 41
    assert_increasing(energies)
    assert_approx_equals(times[37], 0.1)
    assert_approx_equals(times[39], 0.82)
