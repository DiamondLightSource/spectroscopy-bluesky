import math

import bluesky.plan_stubs as bps
import bluesky.plans as bsp
import numpy as np
import pandas as pd
from bluesky.preprocessors import subs_decorator
from bluesky.protocols import Movable, Readable
from dodal.common.types import MsgGenerator
from dodal.devices.common_dcm import BaseDCM

from spectroscopy_bluesky.i18.plans.callback import FitCurves, FitCurvesMaxValue
from spectroscopy_bluesky.i18.utils.stats import (
    bounds_provider,
    normalise_xvals,
    trial_gaussian,
)
from spectroscopy_bluesky.i18.utils.workflow_starter import (
    Visit,
    call_quadratic_workflow,
)


def get_curve_callback() -> FitCurves:
    c = FitCurves()
    c.fit_function = trial_gaussian  # type: ignore
    c.set_transform_function(normalise_xvals)
    # set transform function to make x values relative before fitting
    c.set_bounds_provider(bounds_provider)

    return c


def get_default_max_callback() -> FitCurvesMaxValue:
    c = FitCurvesMaxValue()
    c.set_transform_function(normalise_xvals)
    return c


def generate_start_params():
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
        "Bragg angle range : start = %.4f, step = %.4f, num steps = %d"
        % (bragg_start, bragg_step, bragg_num_steps)
    )
    print(
        f"Gap start, range, end : {gap_start:.4f}, {gap_range:.4f}, {gap_start + gap_range:.4f}"
    )



def undulator_lookuptable_scan(
    bragg_start: float,
    bragg_step: float,
    n_steps: int,
    initial_gap_start: float,
    gap_range: float,
    gap_step: float,
    dcm: BaseDCM,
    bragg_device: Movable,
    undulator_gap_device: Movable,
    detector: Readable,
    use_last_peak=False,
    gap_offset: float = 0,
    fit_parameters: list[float] | None = None,
    curve_fit_callback=None,
    *args,
    **kwargs,
) -> MsgGenerator:
    """
    1. Lookup table: calibrate the DCM.
    2. Measure foil (e.g., Fe, Mg), then record absorption spectrum.
    3. Perform XANES absorption scan; compute first derivative and find argmax.
    4. Adjust Bragg offset to match calibrated value.
    5. For 10–15 points within the element's energy range:
       - Scan the insertion device gap, searching for the maximum.
       - call the workflow engine to apply quadratic interpolation.
    6. TODO: Read previous values from daq-config-server.
    """

    # Generate undulator gap values to be used for each inner scan
    # (values are relative to the start position)
    if fit_parameters is None:
        fit_parameters = []
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
                angles = list(fit_results.keys())[-2:]
                gaps = list(fit_results.values())[-2:]
                grad = (gaps[1] - gaps[0]) / (angles[1] - angles[0])
                expected_peak = (bragg_angle - angles[-1]) * grad + gaps[-1]
                print(
                    f"angles = {angles}, gaps = {gaps}, expected peak gap value = {expected_peak}"
                )
                start_gap = expected_peak - gap_range * 0.5
                print(f"start gap value = {start_gap}")
        else:
            # gap start is current position of undulator gap
            msg = yield from bps.read(dcm.xfine)
            start_gap = msg[undulator_gap_device.name]["value"]
            print(f"Current undulator gap position : {start_gap}")

        gap_points = undulator_points + start_gap + gap_offset

        print(f"Undulator values : {gap_points}")

        if curve_fit_callback is None:
            curve_fit_callback = get_default_max_callback()

        @subs_decorator(curve_fit_callback)
        def processing_decorated_plan(points):
            msg = yield from bsp.list_scan([detector], dcm.idgap, points)
            return msg

        msg = yield from processing_decorated_plan(points=gap_points)

        print(f"Fit results : {curve_fit_callback.results}")

        # save the peak x position from the curve fit result
        # (fitted x values are relative to first point, so add the start gap position)
        fit_results[bragg_angle] = curve_fit_callback.results[0][0][-1] + gap_points[0]
        last_peak_position = fit_results[bragg_angle]

        print(
            f"Fitted peak position : bragg = {bragg_angle}, undulator gap = {last_peak_position}"
        )
        bragg_angle += bragg_step

    print("Peak results:", fit_results)
    peak_df = pd.DataFrame(fit_results)

    visit = Visit(number=3, proposalCode="cm", proposalNumber=40636)
    graphql_url = "http://workflows.diamond.ac.uk/graphql"

    try:
        job_id = call_quadratic_workflow(peak_df, visit, graphql_url)
        print(f"Quadratic workflow submitted, job id: {job_id}")
    except Exception as e:
        print(f"Failed to submit quadratic workflow: {e}")
