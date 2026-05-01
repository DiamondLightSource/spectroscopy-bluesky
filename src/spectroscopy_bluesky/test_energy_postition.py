import h5py
import matplotlib.pyplot as plt
import numpy as np

# from spectroscopy_bluesky.common.quantity_conversion import (
from common.quantity_conversion import (
    bragg_angle_to_energy,
    si_111_lattice_spacing,
)

# from spectroscopy_bluesky.common.xas_scans import (
from common.xas_scans import (
    XasScanParameters,
    XasScanPointGenerator,
)


def create_energy(element, edge):
    params = XasScanParameters(element, edge)
    params.set_from_element_edge()
    params.set_abc_from_gaf()
    gen = XasScanPointGenerator(params)
    grid = gen.calculate_energy_time_grid()
    return grid[:, 0]


def bragg_angle_back_to_energy():
    filename = "/dls/p51/data/2026/cm44254-1/p51-1861-panda1.h5"

    # Data from the XAS lookup table
    energy_from_xas_lookup = create_energy(element="Ar", edge="K")
    print(f"energy is {energy_from_xas_lookup[0:10]}")

    with h5py.File(filename, "r") as f:
        print(list(f.keys()))
        # There can be multiple number of sweeps in a scan
        data = f["INENC1.VAL.Max"][0 : len(energy_from_xas_lookup)]

    rad_data = data / -10000
    energy = bragg_angle_to_energy(si_111_lattice_spacing, rad_data)

    delta = energy - energy_from_xas_lookup
    print(f"Mean is {np.mean(delta)}")
    print(f"Standard Deviation is {np.std(delta)}")
    print(f"Max is {np.max(delta)}")
    print(f"Min is {np.min(delta)}")

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(8, 6))

    # ---- Plot angle ----
    ax1.plot(energy_from_xas_lookup)
    ax1.set_ylabel("Energy")
    ax1.set_title("Energy from XAS lookup table")

    # ---- Plot energy ----
    ax2.plot(energy)
    ax2.set_xlabel("Index")
    ax2.set_ylabel("Energy")
    ax2.set_title("Energy from Nexus File")

    plt.tight_layout()
    plt.show()


bragg_angle_back_to_energy()
