import math

import bluesky.plan_stubs as bps
import bluesky.plans as bsp
import numpy as np
from bluesky.preprocessors import subs_decorator
from bluesky.protocols import Movable, Readable

from spectroscopy_bluesky.i18.plans.curve_fitting import (
    FitCurves,
    FitCurvesMaxValue,
    gaussian_bounds_provider,
    trial_gaussian,
)
from spectroscopy_bluesky.i18.plans.lookup_tables import (
    id_gap_lookup_table_column_names,
    load_lookuptable_curve,
)

fit_curve_callback_gaussian = FitCurves()
fit_curve_callback_gaussian.fit_function = trial_gaussian
# fit_curve_callback_gaussian.set_transform_function(normalise_xvals)

# set transform function to make x values relative before fitting
fit_curve_callback_gaussian.bounds_provider = gaussian_bounds_provider

fit_curve_callback_maxval = FitCurvesMaxValue()
# fit_curve_callback_maxval.set_transform_function(normalise_xvals)


def calculate_gap_parameters(
    lookup_table_file: str,
    bragg_start: float,
    bragg_step: float,
    gap_range_multiplier: float = 2.5,
    **kwargs,
) -> tuple[float, float]:
    undulator_gap_value = load_lookuptable_curve(lookup_table_file, **kwargs)

    # lookup undulator gap at intial and next bragg angle
    gap_bragg_start = undulator_gap_value(bragg_start)
    gap_bragg_next = undulator_gap_value(bragg_start + bragg_step)
    # range of undulator values to be covered by each scan
    gap_range = gap_range_multiplier * (gap_bragg_next - gap_bragg_start)

    # scan start position - to try and get peak signal in the centre of the range
    gap_start = undulator_gap_value(bragg_start) - 0.5 * gap_range

    print(
        f"Gap at initial Bragg angle : {gap_bragg_start:.4f}\n"
        f"Gap at next Bragg angle : {gap_bragg_next:.4f}\n"
        f"Gap scan range : {gap_range:.4f}\n"
        f"Gap scan start value : {gap_start:.4f}"
    )

    return float(gap_start), float(gap_range)


def estimate_next_gap_peak(
    fit_results: list[list[float]], bragg_angle: float
) -> float:
    """Use linear extrapolation to find the next gap start position from last
    two fitted peak positions :
    using :
        gap(bragg_angle) = gap[1] +
                (bragg_angle-bragg[1])*(gap[1]-gap[0])/(bragg[1]-bragg[0])

    (index 1 and 0 are last and previous fitted peak values respectively)
    Args:
        fit_results (list[list[float]]): fitted [bragg angle, gap] values
        bragg_angle (float): bragg angle for gap value estimatation

    Returns:
        float: gap peak position
    """

    # extract last two recorded bragg angle and gap values
    # and extrapolate to compute expected gap value
    # for given bragg_angle

    angles = [val[0] for val in fit_results[-2:]]
    gaps = [val[1] for val in fit_results[-2:]]

    grad = (gaps[1] - gaps[0]) / (angles[1] - angles[0])
    expected_peak = gaps[1] + (bragg_angle - angles[1]) * grad
    print(
        f"angles = {angles}, gaps = {gaps}, expected peak gap value for "
        f"Bragg angle {bragg_angle} = {expected_peak}"
    )

    return expected_peak


def undulator_lookuptable_scan_autogap(
    bragg_start: float,
    bragg_step: float,
    bragg_num_steps: int,
    lookup_table_file: str,
    bragg_motor: Movable,
    undulator_gap_motor,  # needs to Movable and Readable
    d7diode: Readable,
    gap_scan_step_size: float = 0.01,
    gap_range_multiplier: float = 2.5,
    *args,
    **kwargs,
):
    gap_start, gap_range = calculate_gap_parameters(
        lookup_table_file, bragg_start, bragg_step, gap_range_multiplier
    )

    yield from undulator_lookuptable_scan(
        bragg_start,
        bragg_step,
        bragg_num_steps,
        gap_start,
        gap_range,
        gap_scan_step_size,
        bragg_motor,
        undulator_gap_motor,
        d7diode,
        *args,
        **kwargs,
    )


def undulator_lookuptable_scan(
    bragg_start: float,
    bragg_step: float,
    n_steps: int,
    initial_gap_start: float,
    gap_range: float,
    gap_step: float,
    bragg_device: Movable,
    undulator_gap_device,
    detector: Readable,
    use_last_peak: bool = True,
    gap_offset: float = 0,
    fit_parameters: list[float] | None = None,
    output_file: str | None = None,
    curve_fit_callback: FitCurves = fit_curve_callback_gaussian,
    *args,
    **kwargs,
):
    # Generate undulator gap values to be used for each inner scan
    # (values are relative to the start position)
    gap_relative_points = np.linspace(0, gap_range, math.floor(gap_range / gap_step))
    bragg_end = bragg_start + n_steps * bragg_step
    bragg_points = np.linspace(bragg_start, bragg_end, n_steps)

    if output_file is not None:
        print(f"Writing data to file : {output_file}")
        with open(output_file, "w") as myfile:
            myfile.write(
                f"# {id_gap_lookup_table_column_names[0]}, "
                f"{id_gap_lookup_table_column_names[1]}\n"
            )

    adjust_start_gap = True

    # Move undulator to initial position
    yield from bps.mov(undulator_gap_device, initial_gap_start)

    # [bragg angle, gap value] for each angle in bragg_points
    fit_results: list[list[float]] = []

    for bragg_angle in bragg_points:
        print(f"Bragg angle : {bragg_angle}")
        yield from bps.mv(bragg_device, bragg_angle)

        # Determine start position for next gap scan
        if use_last_peak and len(fit_results) > 0:
            # start at last peak position
            gap_start = fit_results[-1][1]

            # Estimate the next start position from last two fitted peaks
            if adjust_start_gap and len(fit_results) > 1:
                expected_peak = estimate_next_gap_peak(fit_results, bragg_angle)

                # start gap value to place expected peak position
                # in middle of the gap scan range

                start_gap = expected_peak - gap_range * 0.5
                print(f"start gap value = {start_gap}")
        else:
            # gap start is current position of undulator gap
            msg = yield from bps.read(undulator_gap_device)
            gap_start = msg[undulator_gap_device.name]["value"]
            print(f"Current undulator gap position : {gap_start}")

        # set of undulator gap values to be scanned
        gap_abs_points = gap_relative_points + gap_start + gap_offset

        print(f"Undulator values : {gap_abs_points}")

        @subs_decorator(curve_fit_callback)
        def processing_decorated_plan(points):
            msg = yield from bsp.list_scan([detector], (undulator_gap_device), points)
            return msg

        msg = yield from processing_decorated_plan(gap_abs_points)

        print(f"Fit results : {curve_fit_callback.results}")

        # (fitted x values are relative to first point, so add the start gap position)
        fit_result = curve_fit_callback.results[0][0][-1]
        # fit is relative to start position
        if fit_result < gap_abs_points[0] or fit_result > gap_abs_points[-1]:
            fit_result += gap_abs_points[0]

        fit_results.append([bragg_angle, fit_result])

        print(
            f"Peak fit method : = {curve_fit_callback=}\n"
            f"Fitted peak position : bragg = {bragg_angle:.4f}, "
            f"undulator gap = {fit_result:.4f}"
        )

        if output_file is not None:
            with open(output_file, "a") as myfile:
                myfile.write(f"{bragg_angle:.6f}\t{fit_result:.6f}\n")

    return fit_results
