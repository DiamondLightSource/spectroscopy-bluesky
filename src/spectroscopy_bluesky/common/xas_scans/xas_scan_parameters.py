import xraydb as xraydb
import math
from dataclasses import dataclass
from scipy.constants import electron_volt, angstrom, hbar, electron_mass
from typing import cast

"""
Parameters needed for calculating energy grid for Xas scan
The names of the parameters matches the XasScanParameters class in GDA,
to allow these objects to be deserialized using json.
Values with defaults of zero can set automatically by setting the element and edge names
and calling set_from_element_edge and set_abc_from_gaf.
"""


@dataclass
class XasScanParameters:
    element: str  # element name (Fe, Mn, Zr etc)
    edge: str  # name of edge (K, L, L1, M2 etc)
    initialEnergy: float = 0
    finalEnergy: float = 0
    edgeEnergy: float = 0
    coreHole: float = 0
    gaf1: float = 30
    gaf2: float = 10
    gaf3: float = 10
    a: float = 0
    b: float = 0
    c: float = 0
    preEdgeStep: float = 5.0
    preEdgeTime: float = 0.5
    edgeStep: float = 0.5
    edgeTime: float = 0.5
    exafsStep: float = 0.04  # Step in energy or k step (depending on exafsStepType)
    exafsTime: float = 0.5
    exafsFromTime: float = 1.0
    exafsToTime: float = 3.0
    kWeighting: float = 3.0
    exafsStepType: str = "k"  # 'E' or 'k'
    exafsTimeType: str = "Constant Time"  # 'Constant time' or 'variable time'
    abGafChoice: str = "Gaf1/Gaf2"

    def lookup_edge_energy(self, edge_name: str|None = None) -> float:
        if edge_name is None:
            edge_name = self.edge
        return cast(float, xraydb.xray_edge(self.element, edge_name, energy_only=True))

    def lookup_core_hole(self, edge_name: str|None = None) -> float:
        if edge_name is None:
            edge_name = self.edge
        return cast(float, xraydb.core_width(self.element, edge_name))

    def set_from_element_edge(self):
        """Set the initial and final energy to default values and lookup the edge and core hole
        energies for the element and edge.
        """
        self.edgeEnergy = self.lookup_edge_energy(self.edge)
        self.coreHole = self.lookup_core_hole(self.edge)
        self.finalEnergy = self.calculate_final_energy(self.edge)
        self.initialEnergy = self.edgeEnergy - 200

    def adjust_a_energy(self):
        """Adjust the 'a' energy to match the last energy in the pre-edge region
        i.e. adjusted 'a' energy = last energy step that is < original 'a' energy
        """
        num_steps = int((self.a - self.initialEnergy) / self.preEdgeStep)
        self.a = self.initialEnergy + num_steps * self.preEdgeStep

    def calculate_final_energy(self, edge_name: str) -> float:
        """Calculate the final energy position based on the edge energy and the edge type

        Args:
            edge_name (str): edge name (one of : K, L1, L2, L3, M1, M2, M3, M4, M5)

        Raises:
            Exception: if edge name was not recognized

        Returns:
            float: final energy
        """
        match edge_name:
            case "K":
                return self.edgeEnergy + 850
            case "L1":
                return self.edgeEnergy + self.wavevector_to_ev(15.0)
            case "L2":
                return self.lookup_edge_energy("L1") - 10
            case "L3":
                return self.lookup_edge_energy("L2") - 10
            case "M1":
                return self.edgeEnergy - 10
            case "M2":
                return self.lookup_edge_energy("M1") - 10
            case "M3":
                return self.lookup_edge_energy("M2") - 10
            case "M4":
                return self.lookup_edge_energy("M3") - 10
            case "M5":
                return self.lookup_edge_energy("M4") - 10

        raise Exception("Could not determine final energy for edge " + edge_name)

    @staticmethod
    def wavevector_to_ev(wavevec_inverse_angstrom: float) -> float:
        """Convert from wave vector (inverse Angstroms) to photon energy (eV)
            using : E = (hbar*k)**2 / 2m

        Args:
            wave_vec_angstrom (float): wave vector (inverse Angstroms)

        Returns:
            (float): photon energy (eV)
        """
        return ((hbar * wavevec_inverse_angstrom / angstrom) ** 2) / (
            2 * electron_mass * electron_volt
        )

    @staticmethod
    def ev_to_wavevector(energy_ev: float) -> float:
        """Convert from photon energy (eV) to wavevector (inverse Angstroms).
           from : E = (hbar*k)**2 / 2m  -> k = sqrt(2mE/hbar)

        Args:
            energy (float): photon energy (eV)

        Returns:
            (float): wavevector (inverse Angstroms)
        """
        wave_vec_si = math.sqrt(2.0 * electron_mass * electron_volt * energy_ev) / hbar
        return wave_vec_si * angstrom

    def set_abc_from_gaf(self):
        """Set the a,b,c energies using the core hole and gaf1, gaf2, gaf3 values"""
        a, b, c = self.calculate_abc_from_gaf()
        self.a = a
        self.b = b
        self.c = c

    def check_abc(self):
        """Set c energy to default value if it's currently zero (i.e. 2*edge energy - b energy)"""
        if self.c == 0:
            self.c = 2 * self.edgeEnergy - self.b

    def calculate_abc_from_gaf(self) -> list[float]:
        core_hole = self.coreHole
        edge_energy = self.edgeEnergy

        a = edge_energy - (self.gaf1 * core_hole)
        b = edge_energy - (self.gaf2 * core_hole)
        if self.gaf3 > 0:
            c = edge_energy + (self.gaf3 * core_hole)
        else:
            c = edge_energy + (self.gaf2 * core_hole)

        return [a, b, c]
