# os.environ['EPICS_CA_SERVER_PORT'] = "6064"  # set the Epics port before other imports, otherwise wrong value is picked up (5054)
import asyncio
import os
import time

from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from databroker import Broker, Header
from i18_bluesky.plans.lookup_tables import (
    fit_lookuptable_curve,
    generate_new_ascii_lookuptable,
)
from i18_bluesky.plans.undulator_lookuptable_plan import undulator_lookuptable_scan
from ophyd import EpicsMotor, EpicsSignalRO
from ophyd.sim import SynAxis, SynGauss
from ophyd_async.epics.motor import Motor


def save_scan_data_ascii_file(header: Header, file_path, file_name_format="scan_%d.txt", float_format="%.4f", include_index=True):
    """
        Save results from running bluesky plan to Ascii file
        Columns are motor positions, followed by detector readouts
    """
    scan_id = header.start.scan_id
    columns = (*header.start.motors, *header.start.detectors)
    full_name = file_path + "/" + file_name_format % (scan_id)
    print(f"Saving data to {full_name}\nColumns : {columns}")
    header.table().to_csv(full_name, sep="\t", columns=columns, float_format=float_format, index=include_index)

class EpicsSignalROWithWait(EpicsSignalRO):
    sleep_time_secs: float = 0.0

    def read(self):
        time.sleep(self.sleep_time_secs)
        return super().read()


class UndulatorCurve(SynGauss):
    def __init__(self, *args, **kwargs):
        self.peak_position_function = None
        self.bragg_motor = None
        super().__init__(*args, **kwargs)

    def _compute(self):
        if self.peak_position_function is not None and self.bragg_motor is not None:
            # update the centre position using peak_position_function with bragg_motor position as parameter
            m = self.bragg_motor.position
            self.center.put(self.peak_position_function(m))
        return super()._compute()


filename = "lookuptable_harmonic1.txt"
beamline_lookuptable_dir = "/dls_sw/i18/software/gda_versions/gda_9_36/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/"
# filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic9.txt"
filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic7.txt"

# load lookuptable from ascii file and fit quadratic curve
undulator_gap_value = fit_lookuptable_curve(filename, show_plot=False)

use_epics_motors = True
beamline = True

pv_prefix = "ws416-"
bragg_pv_name = "BL18I-MO-DCM-01:BRAGG" if beamline else pv_prefix + "MO-SIM-01:M1"
undulator_gap_pv_name = "SR18I-MO-SERVC-01:BLGAPMTR" if beamline else pv_prefix + "MO-SIM-01:M2"
energy_motor_pv_name = "BL18I-MO-DCM-01:ENERGY" if beamline else pv_prefix + "MO-SIM-01:M3"

def make_epics_motor(*args, **kwargs):
    mot = EpicsMotor(*args, **kwargs)
    # mot = Motor(*args, **kwargs)
    if isinstance(mot, EpicsMotor):
        mot.wait_for_connection()
    elif isinstance(mot, Motor):
        asyncio.run(mot.connect())

    return mot


# Setup the motors and detector for the environment
if beamline:
    os.environ['EPICS_CA_SERVER_PORT'] = "5064"

    bragg_motor = make_epics_motor(bragg_pv_name, name="bragg_angle")
    undulator_gap_motor = make_epics_motor(undulator_gap_pv_name, name="undulator_gap_motor")
    energy_motor = make_epics_motor(energy_motor_pv_name, name="energy_motor")
    # d7diode = EpicsSignalRO("BL18I-DI-PHDGN-07:B:DIODE:I", name="d7diode")
    d7diode = EpicsSignalROWithWait("BL18I-DI-PHDGN-07:B:DIODE:I", name="d7diode")
    d7diode.sleep_time_secs = 0.5
else:
    if use_epics_motors:
        bragg_motor = make_epics_motor(bragg_pv_name, name="bragg_angle")
        undulator_gap_motor = make_epics_motor(undulator_gap_pv_name, name="undulator_gap_motor")
        # bragg_motor.wait_for_connection()
        # undulator_gap_motor.wait_for_connection()
        # make sure mres is set to small value to show the small changes in position (e.g. 0.001(
    else:
        bragg_motor = SynAxis(name="bragg_motor", labels={"motors"})
        undulator_gap_motor = SynAxis(name="undulator_gap_motor", labels={"motors"}, delay=0.01)
        undulator_gap_motor.precision = 6  # decimal places of precision in readout value
        undulator_gap_motor.pause = 0

    # Setup diode to return gaussian intensity profile
    d7diode = UndulatorCurve("d7diode", undulator_gap_motor, "undulator_gap_motor",
                             center=0,
                             Imax=1)
    # peak of the intensity depends on position of bragg_motor, and peak position from quadratic curve 'undulator_gap'
    # i.e. peak_position = undulator_gap(bragg_motor.position)
    d7diode.peak_position_function = undulator_gap_value
    d7diode.bragg_motor = bragg_motor
    d7diode.sigma.put(0.01)
    d7diode.trigger()
    d7diode.precision = 5

# Bragg angle start position, stepsize, number of steps
# bragg_start = 55
# bragg_step = 0.3
# bragg_num_steps = 20

import math

si_d_spacing = 5.4310205
def bragg_to_energy(bragg_angle) :
    si_d_spacing*2*math.sin(bragg_angle*math.pi/180.0)

#bragg_start = 11.4; bragg_step = 0.3; bragg_num_steps = 7
#bragg_start = 12.3; bragg_step = 0.3; bragg_num_steps = 4
#30jan2025
# bragg_start = 14.2; bragg_step = 0.5; bragg_num_steps = 5
bragg_start = 17.4; bragg_step = 0.5; bragg_num_steps = 14

# Undulator range : lookup undulator values for Bragg start position and range
gap_start = undulator_gap_value(bragg_start)
gap_end = undulator_gap_value(bragg_start - bragg_step)
# gap_range = 2.5 * (gap_end - gap_start)  # double, to make sure don't miss the peak
gap_range = 2.5 * (gap_end - gap_start)  # double, to make sure don't miss the peak

# gap range and gap offset could be dynamic (computed from scan during scan)
gap_start = undulator_gap_value(bragg_start) - 0.5 * gap_range

print("Bragg angle range : start = %.4f, step = %.4f, num steps = %d"%(bragg_start, bragg_step, bragg_num_steps))
print("Gap start, range, end : %.4f, %.4f, %.4f"%(gap_start, gap_range, gap_start + gap_range))


bec = BestEffortCallback()
RE = RunEngine()
RE.subscribe(bec)

db = Broker.named('temp')
RE.subscribe(db.insert)


# quadratic curve fit parameters are placed in this list
fit_results = []

base_dir="/dls/science/users/ewz97849/bluesky-install/i18-github/i18-bluesky/src/i18_bluesky/plans/offline_testing/"
# sys.exit()

RE(undulator_lookuptable_scan(bragg_start, -bragg_step, bragg_num_steps,
                              gap_start, gap_range, 0.01,
                              bragg_motor, undulator_gap_motor, d7diode,
                              gap_offset=0.0, use_last_peak=True,
                              show_plot=False, fit_parameters=fit_results,
                              output_file=base_dir+"/bl_scan_data_large_range.txt"))

# Generate new lookup table from fit results
bragg_end = bragg_start - bragg_step*bragg_num_steps
bragg_step = 0.01
generate_new_ascii_lookuptable(base_dir+"bl_table_large_range.txt", fit_results, bragg_start, bragg_end, bragg_step)


