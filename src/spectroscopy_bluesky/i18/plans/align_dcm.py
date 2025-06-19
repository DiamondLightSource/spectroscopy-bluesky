import bluesky.plan_stubs as bps
import numpy as np
import pandas as pd
from dodal.common.coordination import inject
from dodal.common.types import MsgGenerator
from dodal.devices.diode import D7Diode, Diode
from scipy.optimize import curve_fit

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

DEFAULT_DCM: DCM = inject("dcm")
DEFAULT_DIODE: Diode = inject("d7diode")


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


def get_gap_points(
    bragg_angle: float,
    fit_results: dict,
    gap_range: float,
    offset: float,
    base_points: list[float],
):
    # Make new set of undulator gap values to be scanned...
    # extract last two recorded bragg angle and gap value
    angles = list(fit_results.keys())[-2:]
    gaps = list(fit_results.values())[-2:]
    gradient = (gaps[1] - gaps[0]) / (angles[1] - angles[0])
    expected_peak = (bragg_angle - angles[-1]) * gradient + gaps[-1]
    print(
        f"angles = {angles}, gaps = {gaps}, expected peak gap value = {expected_peak}"
    )
    start_gap = expected_peak - gap_range * 0.5
    print(f"start gap value = {start_gap}")

    gap_points = base_points + start_gap + offset

    print(f"Undulator values : {gap_points}")
    return gap_points


def align_dcm(
    dcm=DEFAULT_DCM,
    diode: D7Diode = DEFAULT_DIODE,
    sim: bool = False,
    use_last_peak: bool = False,
) -> MsgGenerator:
    """
    Calibrate the DCM by scanning Bragg and ID gap, fitting a Gaussian to diode current.
    """
    # --- Smart scan range setup (copied logic, no import) ---
    bragg_start = 17.4
    bragg_step = 0.5
    bragg_num_steps = 14


    bragg_range = np.linspace(
        bragg_start, bragg_start - bragg_step * (bragg_num_steps - 1), bragg_num_steps
    )

    data = pd.DataFrame(columns=["bragg", "id_gap", "diode_current"])
    # min_idgap_dict = dict.fromkeys(bragg_range, idgap_range[0])

    peak_results = []
    # todo complete the first run
    # gap start is current position of undulator gap
    msg = yield from bps.read(dcm.gap)
    start_gap = msg[dcm.name]["value"]
    print(f"Current undulator gap position : {start_gap}")

    fit_results = {}
    for angle in bragg_range[1:]:
        yield from bps.mv(dcm.bragg, angle)
        fit_idgaps = []
        fit_currents = []
        max_current = -np.inf
        max_idgap = None

        idgap_range = get_gap_points(
            angle, fit_results, gap_range, gap_offset, undulator_points
        )
        # todo adjust dynamically
        for gap in idgap_range:
            yield from bps.mv(dcm.id_gap, gap)
            yield from bps.sleep(1)
            top = yield from bps.rd(diode)
            current = top.value
            data.loc[len(data)] = {
                "bragg": angle,
                "id_gap": gap,
                "diode_current": current,
            }
            if gap >= min_idgap:
                fit_idgaps.append(gap)
                fit_currents.append(current)
                if current > max_current:
                    max_current = current
                    max_idgap = gap
            if len(fit_currents) > 5 and current < 0.1 * max_current:
                break
        if len(fit_currents) < 5:
            continue
        try:
            popt, _ = curve_fit(
                trial_gaussian,
                fit_idgaps,
                fit_currents,
                p0=[max_current, 1.0, max_idgap],
            )
            peak_gap = popt[2]
            peak_results.append({"bragg": angle, "peak_id_gap": peak_gap})
        except Exception as e:
            print(f"Error fitting data for angle {angle}: {e}")
            continue
    print("Peak results:", peak_results)
    peak_df = pd.DataFrame(peak_results)

    visit = Visit(number=3, proposalCode="cm", proposalNumber=40636)
    graphql_url = "http://workflows.diamond.ac.uk/graphql"

    try:
        job_id = call_quadratic_workflow(peak_df, visit, graphql_url)
        print(f"Quadratic workflow submitted, job id: {job_id}")
    except Exception as e:
        print(f"Failed to submit quadratic workflow: {e}")
