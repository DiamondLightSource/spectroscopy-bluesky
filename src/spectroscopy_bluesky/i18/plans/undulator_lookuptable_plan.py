import math

import bluesky.plan_stubs as bps
import bluesky.plans as bsp
import numpy as np
from bluesky.preprocessors import subs_decorator
from bluesky.protocols import Movable, Readable

from spectroscopy_bluesky.i18.plans.curve_fitting import (
    FitCurves,
    FitCurvesMaxValue,
    fit_quadratic_curve,
)
from spectroscopy_bluesky.i18.plans.lookup_tables import save_fit_results


def trial_gaussian(x, a, b, c):
    return a * np.exp(-(((x - c) * b) ** 2))


def bounds_provider(xvals, yvals):
    bounds_a = 0, max(yvals) + 0.1
    bounds_b = 0, 10000

    # compute approximate centre position from weighted x position :
    weighted_centre = sum(np.array(xvals) * np.array(yvals)) / sum(yvals)
    # set the centre range 10% either side of the peak position
    c_range = max(xvals) - min(xvals)
    centre_range = c_range * 0.1
    bounds_c = weighted_centre - centre_range, weighted_centre + centre_range

    return (bounds_a[0], bounds_b[0], bounds_c[0]), (
        bounds_a[1],
        bounds_b[1],
        bounds_c[1],
    )


def normalise_xvals(xvals, yvals):
    return [x - xvals[0] for x in xvals], yvals


def max_value(x, height, peak_position, delta=0.01):
    delta = (max(x) - min(x)) / 1000
    return [height if abs(xval - peak_position) < delta else 0.0 for xval in x]


def max_value_bounds(xvals, yvals):
    return (min(yvals), min(xvals)), (max(yvals), max(xvals))


fit_curve_callback = FitCurves()
fit_curve_callback.fit_function = trial_gaussian
fit_curve_callback.set_transform_function(
    normalise_xvals
)  # set transform function to make x values relative before fitting
fit_curve_callback.set_bounds_provider(bounds_provider)

fit_curve_callback_maxval = FitCurvesMaxValue()
fit_curve_callback_maxval.set_transform_function(normalise_xvals)


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
    fit_parameters: list[float] = None,
    output_file: str = None,
    curve_fit_callback=None,
    *args,
    **kwargs,
):
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
                # angles = list(fit_results.keys())[-2:]
                # last_two_of_interest = list(fit_results)[-2:]
                # angles = last_two_of_interest[0][0]
                angles = list(fit_results.keys())[-2:]
                # gaps = list(fit_results.values())[-2:]
                gaps = list(fit_results.values())[-2:]
                grad = (gaps[1] - gaps[0]) / (angles[1] - angles[0])
                expected_peak = (bragg_angle - angles[-1]) * grad + gaps[-1]
                print(
                    f"angles = {angles}, gaps = {gaps}, "
                    f"expected peak gap value = {expected_peak}"
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
            curve_fit_callback = fit_curve_callback_maxval

        @subs_decorator(curve_fit_callback)
        def processing_decorated_plan(points):
            msg = yield from bsp.list_scan([detector], undulator_gap_device, points)
            return msg

        msg = yield from processing_decorated_plan(gap_points)

        print(f"Fit results : {curve_fit_callback.results}")

        # save the peak x position from the curve fit result
        # (fitted x values are relative to first point, so add the start gap position)
        fit_results[bragg_angle] = curve_fit_callback.results[0][0][-1] + gap_points[0]
        last_peak_position = fit_results[bragg_angle]

        print(
            f"Fitted peak position : bragg = {bragg_angle}, "
            f"undulator gap = {last_peak_position}"
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
