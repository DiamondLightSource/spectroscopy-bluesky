import pathlib
import socket

import bluesky.plan_stubs as bps
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.run_engine import RunEngine
from ophyd_async.core import init_devices
from ophyd_async.epics.motor import Motor
from ophyd_async.sim import SimMotor

from spectroscopy_bluesky.common.devices import (
    FunctionPatternGenerator,
    ReadableWithDelay,
    SimSignalDetector,
)
from spectroscopy_bluesky.i18.plans.curve_fitting import (
    FitCurvesMaxValue,
    trial_gaussian,
)
from spectroscopy_bluesky.i18.plans.lookup_tables import (
    generate_ascii_lookuptable,
    load_fit_results,
    load_lookuptable_curve,
)
from spectroscopy_bluesky.i18.plans.undulator_lookuptable_plan import (
    undulator_lookuptable_scan_autogap,
)

# lookup table in same directory as this script (offline_testing)
beamline_lookuptable_dir = str(pathlib.Path(__file__).parent.resolve())
filename = beamline_lookuptable_dir + "/Si111_harmonic7.txt"

# load lookuptable from ascii file and fit quadratic curve
undulator_gap_value = load_lookuptable_curve(filename, show_plot=False)

use_beamline_motors = False
use_epics_motors = False
use_epics_diode = False

workstation=socket.gethostname().split(".")[0]
pv_prefix = f"ca://{workstation}-"

motors = {
    "bragg_pv_name": ["BL18I-MO-DCM-01:BRAGG", pv_prefix + "MO-SIM-01:M1"],
    "undulator_gap_pv_name": ["SR18I-MO-SERVC-01:BLGAPMTR", pv_prefix + "MO-SIM-01:M2"],
}

mot_index = 0 if use_beamline_motors else 1
bragg_pv_name = motors["bragg_pv_name"][mot_index]
undulator_gap_pv_name = motors["undulator_gap_pv_name"][mot_index]

print(
    f"Epics motor PVs : bragg motor = {bragg_pv_name}, "
    f"undulator gap = {undulator_gap_pv_name}"
)

bec = BestEffortCallback()
bec.enable_plots()

RE = RunEngine()
RE.subscribe(bec)

def make_motor_devices(bragg_pv, undulator_gap_pv):
    bragg_motor = None
    undulator_gap_motor = None
    with init_devices():
        bragg_motor = Motor(bragg_pv, name="bragg_motor")
        undulator_gap_motor = Motor(undulator_gap_pv, name="undulator_gap_motor")

    return bragg_motor, undulator_gap_motor

if use_epics_motors:
    bragg_motor, undulator_gap_motor = make_motor_devices(
        bragg_pv_name, undulator_gap_pv_name
    )
else:
    bragg_motor = SimMotor(name="bragg_motor", instant=True)
    undulator_gap_motor = SimMotor(name="undulator_gap_motor", instant=True)
    # set the velocities to reasonably high values
    RE(bps.mv(bragg_motor.velocity, 10, undulator_gap_motor.velocity, 20))

# Setup the diode
if use_epics_diode:
    with init_devices():
        d7diode = ReadableWithDelay("BL18I-DI-PHDGN-07:B:DIODE:I", name="d7diode")
    d7diode.delay_before_readout = 0.5
else:
    # Setup dummy detector to return gaussian intensity profile
    gaussian_generator = FunctionPatternGenerator()
    gaussian_generator.user_function = trial_gaussian
    gaussian_generator.function_params = [1.0, 10, 0]
    gaussian_generator.noise = 0.1

    d7diode = SimSignalDetector(gaussian_generator.generate_point, name="d7diode")
    d7diode.precision = 10

    # update centre position of Gaussian when Bragg angle changes
    def update_centre(bragg_angle):
        gaussian_generator.function_params[2] = float(undulator_gap_value(bragg_angle))
        print(
            f"Gaussian centre for Bragg angle "
            f"{gaussian_generator.function_params[2]:.4f} "
            f"{bragg_angle:.4f}"
        )

    # Update x, and centre position of curve when bragg angle changes
    def subscribe_values():
        yield from bps.sleep(0)  # to keep RunEngine happy
        bragg_motor.user_readback.subscribe_value(update_centre)
        undulator_gap_motor.user_readback.subscribe_value(gaussian_generator.set_x)

    RE(subscribe_values())

# lookup table in same directory as this script (offline_testing)
beamline_lookuptable_dir = str(pathlib.Path(__file__).parent.resolve())
filename = beamline_lookuptable_dir + "/Si111_harmonic7.txt"

# load lookuptable from ascii file and fit quadratic curve
undulator_gap_value = load_lookuptable_curve(filename, show_plot=False)

bragg_start = 17.5
bragg_end = 12.0
bragg_step = -0.5
bragg_num_steps = int(1 + (bragg_end - bragg_start) / bragg_step)
gap_scan_output_name = beamline_lookuptable_dir + "/gap_scan_results.txt"
curve_fit_callback = FitCurvesMaxValue()

RE(
    undulator_lookuptable_scan_autogap(
        bragg_start,
        bragg_step,
        bragg_num_steps,
        filename,
        bragg_motor,
        undulator_gap_motor,
        d7diode,
        gap_range_multiplier=3,
        use_last_peak=True,
        output_file=gap_scan_output_name,
        curve_fit_callback=curve_fit_callback,
    )
)

# Load the result of undulator-bragg scan
data, fit_params = load_fit_results(gap_scan_output_name, True)

# Generate new lookup table from fit results
bragg_step = 0.01

generate_ascii_lookuptable(
    beamline_lookuptable_dir + "/bl_table_large_range.txt",
    fit_params,
    bragg_start,
    bragg_end,
    bragg_step,
)
