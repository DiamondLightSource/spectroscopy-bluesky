import numpy as np
from numpy import ndarray
import math
from spectroscopy_bluesky.common.xas_scans import XasScanParameters

"""
Class to generate Xas scan grid of (energy, time) values from settings in XasScanParameters object

"""
class XasScanPointGenerator:
    def __init__(self, xas_scan_parameters: XasScanParameters):
        self.params: XasScanParameters = xas_scan_parameters
        self.EXAFS_SMOOTH_COUNT: int = 10
        self.smooth_exafs_region = True
        self.adjust_a_energy = True
    
    def calculate_energy_time_grid(self) -> list[tuple[float, float]]: 
        pre_edge_region = self.create_pre_edge()
        ab_region = self.create_AB_region()
        bc_region = self.create_BC_region()

        # Create energy and time points for exafs region :
        exafs_energies = self.create_exafs_energies()
        exafs_times = [self.params.exafsTime]*len(exafs_energies)

        # Interpolate times in exafs region
        if not self.is_constant_exafs_time():
            exafs_times = self.create_varying_time_exafs(exafs_energies, self.params.exafsFromTime, self.params.exafsToTime)

        # Smooth out the first few energy points in exafs region
        if self.smooth_exafs_region:
            num_energies_to_replace, smoothed_exafs = self.create_smoothed_exafs(self.params.c, self.params.edgeStep, exafs_energies)

            # remove the points from original exafs energy and time lists
            for i in range(num_energies_to_replace):
                exafs_energies.pop(0)
                exafs_times.pop(0)

            # Insert smoothed energy points, using fixed constant time 
            time = exafs_times[0]
            smoothed_exafs.reverse()
            for energy in smoothed_exafs:
                exafs_energies.insert(0, energy)
                exafs_times.insert(0, time)

        # Make 2d array from energy and time values
        exafs_region = np.zeros([len(exafs_energies), 2])
        exafs_region[:,0] = exafs_energies
        exafs_region[:,1] = exafs_times

        # Join all the regions together
        return np.concatenate((pre_edge_region, ab_region, bc_region, exafs_region), axis=0)

    def get_edge_energy(self):
        return self.params.edgeEnergy

    def get_core_hole_energy(self):
        return self.params.coreHole

    def create_pre_edge(self):
        points = self.create_const_step_region(self.params.initialEnergy, self.params.a, 
                           self.params.preEdgeStep)
        return self.create_energy_time_array(points, self.params.preEdgeTime)

    def create_energy_time_array(self, energies, time_value) -> ndarray: 
        arr = np.zeros([len(energies), 2])
        arr[:,0] = energies
        arr[:,1] = time_value
        return arr
    
    def create_AB_region(self):
        points = self.calculateVariableStepRegion(self.params.a, self.params.b,
                                                  self.params.preEdgeStep, self.params.edgeStep)
        return self.create_energy_time_array(points,self.params.preEdgeTime)
    
    
    def create_BC_region(self):
        points = self.create_const_step_region(self.params.b, self.params.c,
                           self.params.edgeStep)
        return self.create_energy_time_array(points,self.params.edgeTime)

    
    def create_exafs_energies(self) -> list[float]:
        if self.is_constant_exafs_energy_step():
            return list(self.create_constant_step_exafs())
        else:
            return self.create_constant_kstep_exafs()
    
    def create_constant_step_exafs(self):
        return self.create_const_step_region(self.params.c, self.params.finalEnergy,
                           self.params.exafsStep, self.params.exafsTime,
                           include_last_point=True)

    def create_constant_kstep_exafs(self) -> list[float]:
        k_start = self.ev_to_wavevector(self.params.c)
        k_end = self.ev_to_wavevector(self.params.finalEnergy)
        k_steps = self.create_const_step_region(k_start, k_end, self.params.exafsStep, include_last_point=True)
        
        # convert wavevector values in back to energy
        return [self.wavevector_to_ev(p) for p in k_steps]
                
      
    def ev_to_wavevector(self, energy: float) -> float:
        """Convert from photon energy (eV) to wavevector (inverse Angstroms) -
        (relative to wavevector at edge energy)
        Uses :py:meth:`XasScanParameters.ev_to_wavevector`

        Args:
            energy (float): photon energy (eV)

        Returns:
            (float): wavevector (inverse Angstroms)
        """
        delta_e = energy - self.params.edgeEnergy
        return XasScanParameters.ev_to_wavevector(delta_e)
    

    def wavevector_to_ev(self, wave_vec_angstrom: float) -> float:
        """Convert from wave vector (inverse Angstroms) to photon energy (eV)
        (relative to edge energy)
        Uses :py:meth:`XasScanParameters.wavevector_to_ev`

        Args:
            wave_vec_angstrom (float): wave vector (inverse Angstroms)

        Returns:
            (float): photon energy (eV)
        """
        return XasScanParameters.wavevector_to_ev(wave_vec_angstrom)+self.params.edgeEnergy

    def create_const_step_region(self, start: float, end: float, step: float, include_last_point: bool =False):
        last_point = end + step if include_last_point else end
        return np.arange(start, last_point, step)
    
    def calculateVariableStepRegion(self, aEnergy: float, bEnergy: float, preEdgeStep: float, edgeStep: float) -> list[float]:
        ds = edgeStep - preEdgeStep
        de = bEnergy - aEnergy
        davg = (edgeStep + preEdgeStep) / 2
        if de > davg:
            steps = de / davg; # how many average step sizes fit between A and B energies
            num_steps = int(steps + 1)
            if num_steps >= 2:
                dh = de - preEdgeStep * num_steps
                aa = (3 * dh / (num_steps**2)) - (ds / num_steps)
                bb = (-2 * dh / (num_steps**3)) + (ds / (num_steps**2))
                energies: list[float] = []
                for i in range(0, num_steps) :
                    energies.append(aEnergy + preEdgeStep * i + aa * (i**2) + bb * (i**3))

                return energies
        raise Exception("Could not calculate energy points for AB region of XAS scan")    
    
    def create_smoothed_exafs(self, cEnergy: float, edgeStep: float, exafsEnergies: list[float]) -> tuple[int, list[float]]:

        # Calculate the number of steps to go from x1 and x2
        # using step size the average of dx1 and dx1
        def calc_num_steps(x1: float, x2: float, dx1: float, dx2: float):
            return int((x2-x1)*2.0/(dx1+dx2)) + 1

        # Don't do any smoothing if there are too few energy points
        if len(exafsEnergies) < self.EXAFS_SMOOTH_COUNT:
            return []

        i = 0
        num_steps = 0
        while num_steps < self.EXAFS_SMOOTH_COUNT:
            kStep = exafsEnergies[i + 1] - exafsEnergies[i]
            num_steps = calc_num_steps(cEnergy, exafsEnergies[i], edgeStep, kStep)
            if num_steps > self.EXAFS_SMOOTH_COUNT:
                break
            i += 1
        
        # i is the number of points in exafsEnergies that should replaced with the smoothed ones
        return i, self.calculateVariableStepRegion(cEnergy, exafsEnergies[i], edgeStep, kStep)
   
    def create_varying_time_exafs(self, energies: list[float], start_time: float, end_time: float) -> list[float]:
        times = []
        const = (end_time-start_time)/math.pow(energies[-1] - energies[0], self.params.kWeighting)
        for energy in energies: 
            times.append(start_time + const*math.pow(energy - energies[0], self.params.kWeighting))
        return times
    
    def is_constant_exafs_energy_step(self):
        return self.params.exafsStepType.lower() == "e"

    def is_constant_exafs_time(self):
        return self.params.exafsTimeType.lower() == "constant time"

def example():
    # Setup the parameters
    params = XasScanParameters("Fe", "K")
    params.set_from_element_edge()
    params.set_abc_from_gaf()
    params.adjust_a_energy()
    params.exafsTimeType = "variable time"

    print("Parameters : {}".format(params))

    # Generate the energy grid values
    generator = XasScanPointGenerator(params)
    generator.smooth_exafs_region = True
    energies = generator.calculate_energy_time_grid() 

    # Plot the energy grid values and step size
    import matplotlib.pyplot as plt
    delta_e = energies[1:-1,0] - energies[0:-2,0]
    point_num = np.arange(len(energies))

    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()
    ax1.set_xlabel("Point number")

    plot1= ax1.plot(energies[:,0], "-r")
    ax1.set_ylabel("Energy [eV]")
    plot2 = ax2.plot(delta_e, "-g")
    ax2.set_ylabel("Step size [eV]")
    ax2.legend(plot1+plot2, ["Energy","Step size"], loc=0) 

    plt.show()

    print("\n\n# Index, energy [eV], collection time [sec]")
    for i,p in enumerate(energies):
        print(i, p[0], p[1])

example()