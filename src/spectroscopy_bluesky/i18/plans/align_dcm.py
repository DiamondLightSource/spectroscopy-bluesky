"""
first, we lookup table - calibrate the DCM
- measure foil, etc Fe, Mg, then absorption spectrum
then the xanes absorption - then derivative, argmax of the first derivative
then Bragg offset is adjusted to match the calibrated value

- for 10-15 points inside the energy range for this element
we scan the gap fo the insertion devise, looking for the maximum
then quadratic interpolation, written into the file,
then GDA probably some interpolation

- todo read previous values using the daq-config-server
- todo take into account a specific harmonic
"""

import bluesky.plan_stubs as bps
import numpy as np
import pandas as pd
from dodal.common.coordination import inject
from dodal.common.types import MsgGenerator
from dodal.devices.diode import D7Diode, Diode
from scipy.optimize import curve_fit

from spectroscopy_bluesky.i18.utils.workflow_starter import (
    Visit,
    call_quadratic_workflow,
)

DEFAULT_DCM: DCM = inject("dcm")
DEFAULT_DIODE: Diode = inject("d7diode")


def trial_gaussian(x, a, b, c):
    return a * np.exp(-(((x - c) * b) ** 2))


def align_dcm(
    dcm=DEFAULT_DCM, diode: D7Diode = DEFAULT_DIODE, sim: bool = False
) -> MsgGenerator:
    """
    Calibrate the DCM by scanning Bragg and ID gap, fitting a Gaussian to diode current.
    """
    # --- Smart scan range setup (copied logic, no import) ---
    bragg_start = 17.4
    bragg_step = 0.5
    bragg_num_steps = 14

    # Dummy undulator mapping for demonstration (replace with real mapping if available)
    def undulator_angle_to_gap_mapping(angle):
        # Example: linear mapping, replace with real calibration
        return 10 + 0.2 * angle

    gap_start = undulator_angle_to_gap_mapping(bragg_start)
    gap_end = undulator_angle_to_gap_mapping(bragg_start - bragg_step)
    gap_range = 2.5 * (gap_end - gap_start)
    gap_start = undulator_angle_to_gap_mapping(bragg_start) - 0.5 * gap_range

    bragg_range = np.linspace(
        bragg_start, bragg_start - bragg_step * (bragg_num_steps - 1), bragg_num_steps
    )
    idgap_range = np.linspace(gap_start, gap_start + gap_range, 10)

    data = pd.DataFrame(columns=["bragg", "id_gap", "diode_current"])
    min_idgap_dict = dict.fromkeys(bragg_range, idgap_range[0])

    peak_results = []
    for angle in bragg_range:
        yield from bps.mv(dcm.bragg, angle)
        min_idgap = min_idgap_dict.get(angle, idgap_range[0])
        fit_idgaps = []
        fit_currents = []
        max_current = -np.inf
        max_idgap = None

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
