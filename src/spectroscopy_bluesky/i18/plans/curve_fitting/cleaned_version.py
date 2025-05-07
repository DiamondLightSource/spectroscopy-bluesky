import asyncio
import math
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
from ophyd.sim import SynAxis, SynGauss
from ophyd_async.epics.motor import Motor

from spectroscopy_bluesky.i18.devices.dcm_to_lookup_table_forwarder import (
    DcmSmartLookupTable,
    LookupTableSettings,
)
from spectroscopy_bluesky.i18.devices.lookup_tables import (
    fit_lookuptable_curve,
    generate_new_ascii_lookuptable,
    save_fit_results,
)

# os.environ['EPICS_CA_SERVER_PORT'] = "6064"  # set the Epics port before other imports, otherwise wrong value is picked up (5054)


def undulator_lookuptable_scan(
    bragg_start: float,
    bragg_step: float,
    n_steps: int,
    initial_gap_start: float,
    gap_range: float,
    gap_step: float,
    bragg_device: Movable,
    undulator_gap_device: Movable, # is this xfine?
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

        def processing_decorated_plan():
            msg = yield from bsp.list_scan([detector], undulator_gap_device, gap_points)  # noqa: B023
            return msg

        msg = yield from processing_decorated_plan()

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

filename = "lookuptable_harmonic1.txt"
beamline_lookuptable_dir = "/dls_sw/i18/software/gda_versions/gda_9_36/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/"  # noqa: E501
# filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic9.txt"
filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic7.txt"

# load lookuptable from ascii file and fit quadratic curve
undulator_angle_to_gap_mapping = fit_lookuptable_curve(filename, show_plot=False)

def call_with_default_values(saving_device: DcmSmartLookupTable, d7diode):
    saving_device.
    bragg_start = 17.4
    bragg_step = 0.5
    bragg_num_steps = 14

    # Undulator range : lookup undulator values for Bragg start position and range
    gap_start = undulator_angle_to_gap_mapping(bragg_start)
    gap_end = undulator_angle_to_gap_mapping(bragg_start - bragg_step)
    gap_range = 2.5 * (gap_end - gap_start)  # double, to make sure don't miss the peak

    # gap range and gap offset could be dynamic (computed from scan during scan)
    gap_start = undulator_angle_to_gap_mapping(bragg_start) - 0.5 * gap_range

    print(
        "Bragg angle range : start = %.4f, step = %.4f, num steps = %d"  # noqa: UP031
        % (bragg_start, bragg_step, bragg_num_steps)
    )

    print(
        f"Gap start, range, end : {gap_start:.4f}, {gap_range:.4f}, {gap_start + gap_range:.4f}"
    )

    base_dir = "/dls/science/users/ewz97849/bluesky-install/i18-github/i18-bluesky/src/spectroscopy_bluesky.i18/plans/offline_testing/"  # noqa: E501
    saving_device.dump_model(
        base_dir + "bl_table_large_range.txt",
        fit_results,
        bragg_start,
        bragg_end,
        bragg_step,
    )

    # Generate new lookup table from fit results
    bragg_end = bragg_start - bragg_step * bragg_num_steps
    bragg_step = 0.01

    # quadratic curve fit parameters are placed in this list
    fit_results = []
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

DEFAULT_DCM: DCM = inject("dcm")
DEFAULT_DIODE: Diode = inject("d7diode")


def align_dcm(
    dcm=DEFAULT_DCM, diode: D7Diode = DEFAULT_DIODE, sim: bool = False
) -> MsgGenerator:  # noqa: E501
    """

    sample stages T1X
    T1Y

    (for tomography also T1Theta)

    two ion chambers

    kb motors, two mirrors vertical and horizontal
    ecah has 2 motors, bend1, bend2
    usually moved simultaneously, but for fine focus separately

    get the gaussian shape IT transmission detector we get the shape


    first, we lookup table - calibrate the DCM
    - measure foil, etc Fe, Mg, then absorption spectrum
    then the xanes absorption - then derivative, argmax of the first derivative
    then Bragg offset is adjusted to match the calibrated value

    second the idgap lookup tables
    - for 10-15 points inside the energy range for this element
    we scan the gap fo the insertion devise, looking for the maximum
    then quadratic interpolation, written into the file,
    then GDA probably some interpolation
    TFG calculates frequency from current via voltage
    so we need to load the panda configuration

    align the pinhole to reduce the scatter -
    400 micron or 200 micron, then centralize it
    usuallly not seen immediately
    FocusingMirror misses curvature
    preparation for the wire stage - check if we have any
    gold wires on the sample stage - scanned in one direction
    first horizonal, vertical
    then record with IT the absorption profile, derviative and fitting
    then changing the bend
    could be 10 iterations, in either direction
    to minimuze the beam size until it changes
    to see the beam shape and the size
    takes usually 30 minutes to go through focusing manually, 2-3 hours

    visual comparison fo the drviative -
    best if without the tails, could be parametrized
    or 50 micron beam - and then defocus to get to that

    golden plate with wires is moved by some other location


    """

    if sim:
        # use patterngenerator
        # make the undulator gap motor to be something virutal
        pass
        # todo will need a device like this https://github.com/DiamondLightSource/dodal/blob/e163f793c0c35fda6a2caf2dc9fb68b45a62971e/src/dodal/devices/zocalo/zocalo_results.py#L111
        # d = event_model.ComposeDescriptor()
        # e = event_model.ComposeEvent()

    else:
        yield from bps.read(diode)
        # use bragg motor
        # dcm.bragg_in_degrees

    yield from {}
