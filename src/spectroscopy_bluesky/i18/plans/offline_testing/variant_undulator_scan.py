import time

from bluesky.run_engine import RunEngine
import bluesky.plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback

from ophyd import EpicsSignalRO
from ophyd_async.epics.motor import Motor
from ophyd_async.sim import SimMotor
from ophyd_async.core import init_devices

from spectroscopy_bluesky.common import sim_gaussian

from spectroscopy_bluesky.i18.plans.lookup_tables import (
    load_lookuptable_curve,
    generate_new_ascii_lookuptable,
)
from spectroscopy_bluesky.i18.plans.undulator_lookuptable_plan import (
    undulator_lookuptable_scan,
    undulator_lookuptable
)

import pathlib

class EpicsSignalROWithWait(EpicsSignalRO):
    sleep_time_secs: float = 0.0

    def read(self):
        time.sleep(self.sleep_time_secs)
        return super().read()

# lookup table in same directory as this script (offline_testing)
beamline_lookuptable_dir = str(pathlib.Path(__file__).parent.resolve())
filename = beamline_lookuptable_dir+"/Si111_harmonic7.txt"

# load lookuptable from ascii file and fit quadratic curve
undulator_gap_value = load_lookuptable_curve(filename, show_plot=False)

use_beamline_motors = True
use_epics_motors = True
use_epics_diode = False

pv_prefix = "ca://ws416-"

motors = {"bragg_pv_name" : ["BL18I-MO-DCM-01:BRAGG", pv_prefix + "MO-SIM-01:M1"],
          "undulator_gap_pv_name" : ["SR18I-MO-SERVC-01:BLGAPMTR", pv_prefix + "MO-SIM-01:M2"]
}

# Turbo slit motors for testing on i20-1
turbo_slit="BL20J-OP-PCHRO-01:TS:XFINE"
turbo_arc="BL20J-OP-PCHRO-01:TS:ARC"

motors["bragg_pv_name"][0] = turbo_slit
motors["undulator_gap_pv_name"][0] = turbo_arc

mot_index = 0 if use_beamline_motors else 1
bragg_pv_name = motors["bragg_pv_name"][mot_index] 
undulator_gap_pv_name = motors["undulator_gap_pv_name"][mot_index]

print("Epics motor PVs : bragg motor = %s , undulator gap = %s"%(bragg_pv_name, undulator_gap_pv_name))

bec = BestEffortCallback()
bec.enable_plots()

RE = RunEngine()
RE.subscribe(bec)

def make_motor_devices(bragg_pv, undulator_gap_pv) :
    bragg_motor = None
    undulator_gap_motor = None
    with init_devices() :
        bragg_motor = Motor(bragg_pv, name="bragg_motor")
        undulator_gap_motor = Motor(undulator_gap_pv, name="undulator_gap_motor")
        
    return bragg_motor, undulator_gap_motor

bragg_motor, undulator_gap_motor, d7diode = None, None, None

if use_epics_motors :
    bragg_motor, _ = make_motor_devices(bragg_pv_name, undulator_gap_pv_name)
    # use similated motor for testing on i20-1
    undulator_gap_motor = SimMotor(name="undulator_gap_motor", instant=True)
    RE(bps.mv(undulator_gap_motor.velocity, 10))
else :
    bragg_motor = SimMotor(name="bragg_motor", instant=True)
    undulator_gap_motor = SimMotor(name="undulator_gap_motor", instant=True)
    # set the velocities to reasonably high values
    RE(bps.mv(bragg_motor.velocity, 10, undulator_gap_motor.velocity, 10))

# Setup the diode
if use_epics_diode :
    d7diode = EpicsSignalROWithWait("BL18I-DI-PHDGN-07:B:DIODE:I", name="d7diode")
    d7diode.sleep_time_secs = 0.5
else:
    # Setup dummy detector to return gaussian intensity profile
    gaussian_generator = sim_gaussian.GaussianPatternGenerator()
    sim_gaussian_detector = sim_gaussian.SimSignalDetector(gaussian_generator.generate_point, name="sim_gaussian")

    # update centre position of Gaussian when Bragg angle changes
    def update_centre(bragg_angle) :
        print("############ update_centre called #############")
        gaussian_generator.centre = undulator_gap_value(bragg_angle)
        print("Gaussian centre for Bragg angle %.4f : %.4f "%(gaussian_generator.centre, bragg_angle))
    
    # Update centre position of curve when bragg angle changes
    bragg_motor.user_readback.subscribe_value(update_centre)

    # Update x position on curve when undulator gap changes
    undulator_gap_motor.user_readback.subscribe_value(gaussian_generator.set_x)

    # set the width 
    gaussian_generator.sigma = 0.02
    gaussian_generator.noise = 0.05
    d7diode = sim_gaussian_detector

    d7diode.precision = 5

bragg_start = 17.5
bragg_end = 12.0
bragg_step = -0.5
bragg_num_steps = int(1+(bragg_end-bragg_start)/bragg_step) # 14

RE(undulator_lookuptable(bragg_start, bragg_step, bragg_num_steps,
                      filename, bragg_motor, undulator_gap_motor, d7diode,
                      gap_range_multiplier=3, use_last_peak=True))

"""
fit_results = []
RE(
    undulator_lookuptable_scan(
        bragg_start,
        -bragg_step,
        bragg_num_steps,
        gap_start,
        gap_range,
        0.01,
        bragg_motor,
        undulator_gap_motor,
        d7diode,
        gap_offset=0.0,
        use_last_peak=True,
        show_plot=False,
        fit_parameters=fit_results,
        output_file=beamline_lookuptable_dir + "/bl_scan_data_large_range.txt",
    )
)
"""

"""
# Generate new lookup table from fit results
bragg_end = bragg_start - bragg_step * bragg_num_steps
bragg_step = 0.01
generate_new_ascii_lookuptable(
    beamline_lookuptable_dir + "/bl_table_large_range.txt",
    fit_results,
    bragg_start,
    bragg_end,
    bragg_step,
)

"""