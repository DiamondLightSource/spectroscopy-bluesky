import bluesky.plan_stubs as bps
import numpy as np
import pandas as pd
from dodal.common.coordination import inject
from dodal.common.types import MsgGenerator
from dodal.devices.diode import D7Diode, Diode

DEFAULT_DCM: DCM = inject("dcm")
DEFAULT_DIODE: Diode = inject("d7diode")


def trial_gaussian(x, a, b, c):
    return a * np.exp(-(((x - c) * b) ** 2))


def align_dcm(
    dcm=DEFAULT_DCM, diode: D7Diode = DEFAULT_DIODE, sim: bool = False
) -> MsgGenerator:  # noqa: E501
    """
    first, we lookup table - calibrate the DCM
    - measure foil, etc Fe, Mg, then absorption spectrum
    then the xanes absorption - then derivative, argmax of the first derivative
    then Bragg offset is adjusted to match the calibrated value

    - for 10-15 points inside the energy range for this element
    we scan the gap fo the insertion devise, looking for the maximum
    then quadratic interpolation, written into the file,
    then GDA probably some interpolation
    """
    # read previous values using the daq-config-server

    # todo take into account a specific harmonic
    data = pd.DataFrame(columns=["bragg", "id_gap", "diode_current"])
    bragg_range = np.linspace(0.1, 0.5, 10)  # example range for Bragg angle
    idgap_range = np.linspace(0.1, 0.5, 10)  # example range for ID gap

    # todo this is actually from the previous scan, we should read it from the file
    min_idgap_dict = dict.fromkeys(bragg_range, 0.15)  # Replace with real values

    peak_results = []
    # outer loop for the Bragg angle
    for angle in bragg_range:
        # set the Bragg angle
        yield from bps.mv(dcm.bragg, angle)
        min_idgap = min_idgap_dict.get(angle, 0.15)  # default value if not found
        fit_idgaps = []
        fit_currents = []
        max_current = -np.inf
        max_idgap = None
        peak_found = False

        # inner loop for the ID gap
        for gap in idgap_range:
            # set the ID gap
            yield from bps.mv(dcm.id_gap, gap)

            # measure the diode current
            yield from bps.sleep(1)
            top = yield from bps.rd(diode)
            current = top.value
            data.loc[len(data)] = {
                "bragg": angle,
                "id_gap": gap,
                "diode_current": current,
            }
            # also break the loop if we're past the peak
            if gap >= min_idgap:
                fit_idgaps.append(gap)
                fit_currents.append(current)
                if current > max_current:
                    max_current = current
                    max_idgap = gap
            # if current readout drops below 10% of the maximum, we assume we passed the peak
            if len(fit_currents) > 5 and current < 0.1 * max_current:
                peak_found = True
            break
        if len(fit_currents) < 5:
            # not enough data points to fit, skip this angle
            continue
        # fit the data to a Gaussian function
        try:
            from scipy.optimize import curve_fit

            popt, _ = curve_fit(
                trial_gaussian,
                fit_idgaps,
                fit_currents,
                p0=[max_current, 1.0, max_idgap],
            )
            peak_gap = popt[2]
            # NOTE we do not need the peak value, we need the peak gap (argmax of the fit)
            peak_results.append({"bragg": angle, "peak_id_gap": peak_gap})

        except Exception as e:
            print(f"Error fitting data for angle {angle}: {e}")
            continue
    print("Peak results:", peak_results)
    # save the results to a DataFrame
    peak_df = pd.DataFrame(peak_results)
    # later on marimo workflow will read that file and generate the GDA file.

    # --- Submit peak_df to quadratic workflow ---
    from spectroscopy_bluesky.i18.devices.workflow_starter import (
        Visit,
        call_quadratic_workflow,
    )

    # Example: fill in with actual visit info
    visit = Visit(number=1, proposalCode="mg", proposalNumber=36964)
    graphql_url = (
        "http://workflows.diamond.ac.uk/graphql"  # Replace with actual endpoint
    )

    try:
        job_id = call_quadratic_workflow(peak_df, visit, graphql_url)
        print(f"Quadratic workflow submitted, job id: {job_id}")
    except Exception as e:
        print(f"Failed to submit quadratic workflow: {e}")
