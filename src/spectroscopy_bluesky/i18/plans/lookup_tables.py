import json
import math

import numpy as np
import pandas as pd

from spectroscopy_bluesky.i18.plans.curve_fitting import fit_quadratic_curve, quadratic

"""
Names of the columns in the ID gap lookup table files
"""
id_gap_lookup_table_column_names = ["Bragg [deg]", "ID gap [mm]"]
lookup_table_kwargs = {"float_format": "%9.5f", "sep": "\t", "index": None}


def load_ascii_lookuptable(filename, lines_to_skip=2):
    """
     Load 2-colummn x,y Ascii data from file and convert to numbers
    (optionally skipping the first few lines)

     :param filename:
     :param lines_to_skip how many lines to skip before storing the data
     :return: list containing the x, y value on each line [ (x1,y1), (x2,y2) ...]

    """
    print(f"Loading ascii lookup table from {filename}")
    dataframe = pd.read_csv(
        filename,
        sep=" ",
        skiprows=lines_to_skip,
        names=id_gap_lookup_table_column_names,
    )
    dataframe.info()
    return [(v[0], v[1]) for v in dataframe.values]


def lookup_value(
    y_search, func, range_min=0, range_max=100, tolerance=1e-6, max_iters=20
):
    """
    Lookup x value for a curve y(x), such that y_search = y(x)
    Uses interval bisection to reach desired accuracy tolerance,
    up to maxiumum number of iterations

    """

    def eval_func(x_pos):
        return x_pos, func(x_pos)

    def in_range(v, v1, v2):
        return min(v1, v2) < v < max(v1, v2)

    # evaluate func at lower and upper x bounds :
    lower = eval_func(range_min)
    upper = eval_func(range_max)

    iter_num = 0

    best_y = y_search + 100

    while iter_num < max_iters and math.fabs(best_y - y_search) > tolerance:
        # evaluate function at midpoint
        mid = eval_func((lower[0] + upper[0]) / 2.0)

        # update upper, lower bound depending on midpoint y value relative to y_search
        if in_range(y_search, lower[1], mid[1]):
            upper = mid
        else:
            lower = mid
        best_y = (lower[1] + upper[1]) / 2.0
        iter_num += 1
        # print(lower, upper)

    # return best x value
    return (lower[0] + upper[0]) / 2.0


from scipy.interpolate import CubicSpline


def load_lookuptable_curve(filename, interpolate=True, **kwargs):
    """Load undulator gap lookup table from Ascii file
    and return a function that returns undulator gap for a given Bragg angle

    :param filename:
    :param kwargs:
    :param interpolate (default=True) If true, function uses interpolation to evaluate
    undulator gap, else function is quadratic fit to the values.

    :return: function that returns undulator gap value for a given Bragg angle

    """
    vals = load_ascii_lookuptable(filename, lines_to_skip=2)

    if interpolate:
        values = sorted(load_ascii_lookuptable(filename))
        return CubicSpline([v[0] for v in values], [v[1] for v in values])

    params, cov = fit_quadratic_curve(
        [v[0] for v in vals], [v[1] for v in vals], **kwargs
    )

    def best_undulator_gap(angle):
        return quadratic(angle, *params)

    return best_undulator_gap


def save_fit_results(filename, bragg_angles, gap_values, fit_params=None):
    """
        Save results from running
        :py:func:`spectroscopy_bluesky.i18.plans.undulator_lookuptable_scan` plan to Ascii file
        The top of the file contains :
        <li> Two lines of header showing fit parameters (if fit_params is set)
        <li> One header line showing the column names ('Bragg' and 'ID gap')
        <li> Two columns of data : bragg angle and undulator gap

    :param filename:
    :param bragg_angles: list of bragg angles
    :param gap_values: list of undulator gap values
    :param fit_params: optional fit parameters
      (quadratic fit to the bragg angle - undulator gap profile)

    :return: pandas dataframe of the bragg angle, undulator gap values

    """
    # Create Pandas dataframe containing the fitted values
    dataframe = pd.DataFrame(
        {
            "# " + id_gap_lookup_table_column_names[0]: bragg_angles,
            id_gap_lookup_table_column_names[1]: gap_values,
        }
    )

    print(f"Saving fit parameters and bragg angle undulator values to {filename}")
    with open(filename, "w") as f:
        if fit_params is not None:
            json_string = json.dumps(fit_params.tolist())
            f.write(
                f"# Quadratic fit parameters (x = Bragg, gap = a + b*x + c*x*x)\n# {json_string}\n"  # noqa: E501
            )
        dataframe.to_csv(f, **lookup_table_kwargs)

    return dataframe


def load_fit_results(filename, fit_quadratic=False):
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

    if fit_quadratic:
        fit_params = fit_quadratic_curve(
            dataframe[dataframe.columns[0]], dataframe[dataframe.columns[1]]
        )

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
