import json
import math

import numpy as np
import pandas as pd
from src.spectroscopy_bluesky.i18.utils.stats import quadratic

from spectroscopy_bluesky.i18.devices.curve_fitting import (
    fit_quadratic_curve,
)


def fit_lookuptable_curve(filename, **kwargs):
    vals = load_ascii_lookuptable(filename, lines_to_skip=2)
    params, cov = fit_quadratic_curve(vals, **kwargs)

    def best_undulator_gap(angle):
        return quadratic(angle, *params)

    return best_undulator_gap


def save_fit_results(filename, bragg_angles, gap_values, fit_params=None):
    """
     
    :return: pandas dataframe of the bragg angle, undulator gap values

    """
    # Create Pandas dataframe containing the fitted values
    dataframe = pd.DataFrame(
        {
            "# " + id_gap_lookup_table_column_names[0]: bragg_angles,
            id_gap_lookup_table_column_names[1]: gap_values,
        }
    )

    save_dataframe_to_fs(filename, fit_params, dataframe)

    return dataframe


def save_dataframe_to_fs(filename, fit_params, dataframe: pd.DataFrame) -> None:
    print(f"Saving fit parameters and bragg angle undulator values to {filename}")
    with open(filename, "w") as f:
        if fit_params is not None:
            json_string = json.dumps(fit_params.tolist())
            f.write(
                f"# Quadratic fit parameters (x = Bragg, gap = a + b*x + c*x*x)\n# {json_string}\n"  # noqa: E501
            )
        dataframe.to_csv(f, **lookup_table_kwargs)


def load_fit_results(filename):
    """
        Load fit results from Ascii file (as produced by :py:func:`save_fit_results`
    :param filename:
    :return: tuple containing :
      pandas dataframe of the bragg angle, undulator values,
        and the fit_parameters (if present in the file)
    """
    dataframe = pd.read_csv(
        filename,
        comment="#",
        sep=r"\s+",
        header=None,
        names=id_gap_lookup_table_column_names,
    )
    fit_params = None
    with open(filename) as f:
        if "Quadratic" in f.readline():
            fit_params_string = f.readline().replace("#", "")
            fit_params = json.loads(fit_params_string)

    return dataframe, fit_params


def generate_new_ascii_lookuptable(
    filename, fit_parameters, bragg_start, bragg_end, bragg_step
):
    step = abs(bragg_step) if bragg_start < bragg_end else -abs(bragg_step)
    bragg_vals = np.arange(bragg_start, bragg_end + bragg_step, step).tolist()
    bragg_vals.extend([bragg_end])  # add the final bragg angle value
    gap_vals = [quadratic(v, *fit_parameters) for v in bragg_vals]
    header = "# bragg    idgap\n"
    with open(filename, "w") as f:
        f.write(header)
        # setup the dataframe and write to Ascii file
        dataframe = pd.DataFrame(
            {
                id_gap_lookup_table_column_names[0]: bragg_vals,
                id_gap_lookup_table_column_names[1]: gap_vals,
            }
        )
        dataframe.to_csv(f, header=["Units", "Deg mm"], **lookup_table_kwargs)


if __name__ == "__main__":
    filename = "lookuptable_harmonic1.txt"
    # beamline_lookuptable_dir = "/dls_sw/i18/software/gda_versions/gda_9_36/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/"  # noqa: E501
    # filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic9.txt"
    filename = "/tmp/fits.txt"
    dataframe = load_fit_results(filename)

    print(dataframe)
