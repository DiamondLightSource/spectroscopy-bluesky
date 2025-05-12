import asyncio
import os
import time

import bluesky.plan_stubs as bps
import bluesky.plans as bsp
import numpy as np
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.preprocessors import subs_decorator
from bluesky.protocols import Movable, Readable
from databroker import Broker
from dodal.common.types import MsgGenerator
from ophyd import EpicsMotor, EpicsSignalRO
from ophyd.sim import SynAxis, SynGauss
from ophyd_async.epics.motor import Motor

from spectroscopy_bluesky.i18.devices.lookup_tables import (
    fit_lookuptable_curve,
    generate_new_ascii_lookuptable,
    save_fit_results,
)

# set the Epics port before other imports, otherwise wrong value is picked up (5054)
# os.environ['EPICS_CA_SERVER_PORT'] = "6064"


def undulator_lookuptable_scan(
    bragg_start: float,
    bragg_step: float,
    n_steps: int,
    initial_gap_start: float,
    gap_range: float,
    gap_step: float,
    bragg_device: Movable,
    undulator_gap_device: Movable,
    detector: Readable,
    use_last_peak=False,
    gap_offset: float = 0,
    fit_parameters: list[float] | None = None,
    output_file: str | None = None,
    curve_fit_callback=None,
    *args,
    **kwargs,
) -> MsgGenerator:
    # Generate undulator gap values to be used for each inner scan
    # (values are relative to the start position)
    undulator_points = np.linspace(0, gap_range, math.floor(gap_range / gap_step))
    bragg_end = bragg_start + n_steps * bragg_step
    bragg_points = np.linspace(bragg_start, bragg_end, n_steps)

    adjust_start_gap = True

    # Move undulator to initial position
    yield from bps.mov(undulator_gap_device, initial_gap_start)

    last_peak_position = None
    fit_results = {}

    for bragg_angle in bragg_points:
        print(f"Bragg angle : {bragg_angle}")
        yield from bps.mov(bragg_device, bragg_angle)

        # Make new set of undulator gap values to be scanned...
        if use_last_peak and last_peak_position is not None:
            # gap start is last peak position
            start_gap = last_peak_position

            if adjust_start_gap and len(fit_results) > 1:
                # extract last two recorded bragg angle and gap value
                angles = list(fit_results.keys())[-2:]
                gaps = list(fit_results.values())[-2:]
                grad = (gaps[1] - gaps[0]) / (angles[1] - angles[0])
                expected_peak = (bragg_angle - angles[-1]) * grad + gaps[-1]
                print(
                    f"angles = {angles}, gaps = {gaps}, expected peak gap value = {expected_peak}"  # noqa: E501
                )
                start_gap = expected_peak - gap_range * 0.5
                print(f"start gap value = {start_gap}")
        else:
            # gap start is current position of undulator gap
            msg = yield from bps.read(undulator_gap_device)
            start_gap = msg[undulator_gap_device.name]["value"]
            print(f"Current undulator gap position : {start_gap}")

        gap_points = undulator_points + start_gap + gap_offset

        print(f"Undulator values : {gap_points}")

        if curve_fit_callback is None:
            fit_curve_callback = FitCurves()
            fit_curve_callback.fit_function = trial_gaussian
            fit_curve_callback.set_transform_function(
                normalise_xvals
            )  # set transform function to make x values relative before fitting
            fit_curve_callback.set_bounds_provider(bounds_provider)

            fit_curve_callback_maxval = FitCurvesMaxValue()
            fit_curve_callback_maxval.set_transform_function(normalise_xvals)
            curve_fit_callback = fit_curve_callback_maxval

        @subs_decorator(curve_fit_callback)
        def processing_decorated_plan():
            msg = yield from bsp.list_scan([detector], undulator_gap_device, gap_points)  # noqa: B023
            return msg

        msg = yield from processing_decorated_plan()

        print(f"Fit results : {curve_fit_callback.results}")

        # save the peak x position from the curve fit result
        # (fitted x values are relative to first point, so add the start gap position)
        fit_results[bragg_angle] = curve_fit_callback.results[0][0][-1] + gap_points[0]
        last_peak_position = fit_results[bragg_angle]

        print(
            f"Fitted peak position : bragg = {bragg_angle}, undulator gap = {last_peak_position}"  # noqa: E501
        )
        bragg_angle += bragg_step

    fit_params, cov = fit_quadratic_curve(fit_results, **kwargs)

    if fit_parameters is not None:
        fit_parameters.clear()
        fit_parameters.extend(fit_params)

    # save the fitted peak positions to Ascii file
    if output_file is not None:
        save_fit_results(
            output_file, fit_results.keys(), fit_results.values(), fit_params
        )

    return fit_params


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
            # update the centre position using peak_position_function
            #  with bragg_motor position as parameter
            m = self.bragg_motor.position
            self.center.put(self.peak_position_function(m))
        return super()._compute()


filename = "lookuptable_harmonic1.txt"
beamline_lookuptable_dir = "/dls_sw/i18/software/gda_versions/gda_9_36/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/"  # noqa: E501
# filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic9.txt"
filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic7.txt"

# load lookuptable from ascii file and fit quadratic curve
undulator_gap_value = fit_lookuptable_curve(filename, show_plot=False)

use_epics_motors = True
beamline = True

pv_prefix = "ws416-"
bragg_pv_name = "BL18I-MO-DCM-01:BRAGG" if beamline else pv_prefix + "MO-SIM-01:M1"
undulator_gap_pv_name = (
    "SR18I-MO-SERVC-01:BLGAPMTR" if beamline else pv_prefix + "MO-SIM-01:M2"
)
energy_motor_pv_name = (
    "BL18I-MO-DCM-01:ENERGY" if beamline else pv_prefix + "MO-SIM-01:M3"
)


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
    os.environ["EPICS_CA_SERVER_PORT"] = "5064"

    bragg_motor = make_epics_motor(bragg_pv_name, name="bragg_angle")
    undulator_gap_motor = make_epics_motor(
        undulator_gap_pv_name, name="undulator_gap_motor"
    )
    energy_motor = make_epics_motor(energy_motor_pv_name, name="energy_motor")
    # d7diode = EpicsSignalRO("BL18I-DI-PHDGN-07:B:DIODE:I", name="d7diode")
    d7diode = EpicsSignalROWithWait("BL18I-DI-PHDGN-07:B:DIODE:I", name="d7diode")
    d7diode.sleep_time_secs = 0.5
else:
    if use_epics_motors:
        bragg_motor = make_epics_motor(bragg_pv_name, name="bragg_angle")
        undulator_gap_motor = make_epics_motor(
            undulator_gap_pv_name, name="undulator_gap_motor"
        )
        # bragg_motor.wait_for_connection()
        # undulator_gap_motor.wait_for_connection()
        # make sure mres is set to small value
        # to show the small changes in position (e.g. 0.001(
    else:
        bragg_motor = SynAxis(name="bragg_motor", labels={"motors"})
        undulator_gap_motor = SynAxis(
            name="undulator_gap_motor", labels={"motors"}, delay=0.01
        )
        undulator_gap_motor.precision = (
            6  # decimal places of precision in readout value
        )
        undulator_gap_motor.pause = 0

    # Setup diode to return gaussian intensity profile
    d7diode = UndulatorCurve(
        "d7diode", undulator_gap_motor, "undulator_gap_motor", center=0, Imax=1
    )
    # peak of the intensity depends on position of bragg_motor,
    # and peak position from quadratic curve 'undulator_gap'
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


# bragg_start = 11.4; bragg_step = 0.3; bragg_num_steps = 7
# bragg_start = 12.3; bragg_step = 0.3; bragg_num_steps = 4
# 30jan2025
# bragg_start = 14.2; bragg_step = 0.5; bragg_num_steps = 5
bragg_start = 17.4
bragg_step = 0.5
bragg_num_steps = 14

# Undulator range : lookup undulator values for Bragg start position and range
gap_start = undulator_gap_value(bragg_start)
gap_end = undulator_gap_value(bragg_start - bragg_step)
# gap_range = 2.5 * (gap_end - gap_start)  # double, to make sure don't miss the peak
gap_range = 2.5 * (gap_end - gap_start)  # double, to make sure don't miss the peak

# gap range and gap offset could be dynamic (computed from scan during scan)
gap_start = undulator_gap_value(bragg_start) - 0.5 * gap_range

print(
    "Bragg angle range : start = %.4f, step = %.4f, num steps = %d"  # noqa: UP031
    % (bragg_start, bragg_step, bragg_num_steps)
)
print(
    f"Gap start, range, end : {gap_start:.4f}, {gap_range:.4f}, {gap_start + gap_range:.4f}"
)


bec = BestEffortCallback()
RE = RunEngine()
RE.subscribe(bec)

db = Broker.named("temp")
RE.subscribe(db.insert)


# quadratic curve fit parameters are placed in this list
fit_results = []

base_dir = "/dls/science/users/ewz97849/bluesky-install/i18-github/i18-bluesky/src/spectroscopy_bluesky.i18/plans/offline_testing/"  # noqa: E501
# sys.exit()

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
        output_file=base_dir + "/bl_scan_data_large_range.txt",
    )
)

# Generate new lookup table from fit results
bragg_end = bragg_start - bragg_step * bragg_num_steps
bragg_step = 0.01
generate_new_ascii_lookuptable(
    base_dir + "bl_table_large_range.txt",
    fit_results,
    bragg_start,
    bragg_end,
    bragg_step,
)
