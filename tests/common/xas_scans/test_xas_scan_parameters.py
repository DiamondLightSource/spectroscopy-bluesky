from spectroscopy_bluesky.common.xas_scans import XasScanParameters


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

    return params


def test_energy_region_defaults():
    params = XasScanParameters("Mn", "K")
    params.set_from_element_edge()
    params.set_abc_from_gaf()

    edge_energy = 6539.0
    core_hole_energy = 1.16

    assert params.edgeEnergy == edge_energy
    assert params.coreHole == core_hole_energy
    assert params.initialEnergy == edge_energy - 200
    assert params.finalEnergy == edge_energy + 850
    assert params.a == edge_energy - core_hole_energy * 30
    assert params.b == edge_energy - core_hole_energy * 10
    assert params.c == edge_energy + core_hole_energy * 10


def test_adjust_a_energy():
    params = XasScanParameters("Mn", "K")
    params.set_from_element_edge()
    params.set_abc_from_gaf()

    def num_energies():
        return (params.a - params.initialEnergy) / params.preEdgeStep

    assert num_energies() % 1 > 0

    params.adjust_a_energy()
    assert num_energies() % 1 == 0
