from collections.abc import Callable
from typing import cast

import matplotlib.pyplot as plt
import numpy as np
from bluesky.callbacks.core import CollectThenCompute
from numpy.typing import NDArray
from scipy.optimize import curve_fit


class FitCurves(CollectThenCompute):
    """
    Callback listener that processes collected documents and fits detector
    data with curve :
    <li>Single curve for 1-dimensional line scan,
    <li> N curves for grid scans with shape NxM (M points per curve).

    Uses scipy curve_fit function for curve fitting
    fit_function -> function to be used during fitting
    fit_bounds -> range for each parameter to be used when fitting.
     A tuple of (min, max) value for each parameter.
     e.g. for parameters a, b,c : ( (min a, max a), (min b, max b), (min c, max c))
    """

    def __init__(self):
        super().__init__()
        self.fit_function: Callable[[*tuple[float]], float]
        self.fit_bounds = None
        self.results = []

        # A function to be applied to the x and y values before curve fitting
        self.transform_function : Callable[
            [list[float], list[float]], tuple[list[float], list[float]]
        ] | None = None

        self.bounds = None  # static bounds

        # function that provides bounds (min, max) based on list of x and y values
        self.bounds_provider: Callable[
            [list[float], list[float]], tuple[float, float]
        ] | None = None

    def start(self, doc):
        self.results = []
        self.reset()
        self.start_doc: dict = doc
        super().start(doc)

    def do_fitting(self, xvals, yvals):
        bounds = None
        if self.bounds is not None:
            bounds = self.bounds
        if self.bounds_provider is not None:
            bounds = self.bounds_provider(xvals, yvals)
            print(f"Bounds from {self.bounds_provider.__name__} : {bounds}")

        if bounds is None:
            return curve_fit(self.fit_function, xvals, yvals)
        else:
            return curve_fit(self.fit_function, xvals, yvals, bounds=bounds)

    def determine_scan_shape(self):
        # Extract information about scan shape from start document :
        scan_shape = self.start_doc.get("shape")
        if scan_shape is None:
            scan_shape = [self.start_doc["num_points"]]
        return scan_shape

    def extract_data(self):
        """Extract the x and y values (i.e. position of motor being
        moved and detector readout) from the event documents"""
        motor_names = self.start_doc["motors"]
        inner_loop_motor = motor_names[len(motor_names) - 1]
        det_name = self.start_doc["detectors"][0]

        events = cast(dict, self._events)
        xvals = [e["data"][inner_loop_motor] for e in events]

        def get_det_data_name(event: dict):
            return [n for n in event["data"].keys() if n.startswith(det_name)]

        det_data_name = get_det_data_name(events[0])[0]

        yvals = [e["data"][det_data_name] for e in events]
        return xvals, yvals

    def set_transform_function(self, transform_function):
        """
            A function to be applied to the x and y values before curve fitting
            i.e. xvals_to_fit, yvals_to_fit = transform_function(xvals, yvals)

        :param transform_function: takes the xvalues, yvalues and returns
        new set of values
        :return:
        """
        self.transform_function = transform_function

    def set_bounds_provider(self, bounds_provider):
        """Set a function to be used to compute the bounds to be used when fitting
        The xvals and yvals are passed to the function, and it should
        return a tuple of the bounds ( (lower_bounds), (upper_bounds))

        """
        self.bounds_provider = bounds_provider

    def compute(self):
        """This method is called at run-stop time by the superclass."""
        scan_shape = self.determine_scan_shape()
        print(f"Scan shape : {str(scan_shape)}")
        readouts_per_row = scan_shape[len(scan_shape) - 1]
        num_events = len(self._events)

        # list of x and detector value for each event
        xvals, yvals = self.extract_data()

        if self.transform_function is not None:
            xvals, yvals = self.transform_function(xvals, yvals)

        self.results = []
        for i in range(0, num_events, readouts_per_row):
            param, cov = self.do_fitting(
                xvals[i : i + readouts_per_row], yvals[i : i + readouts_per_row]
            )
            self.results.append([param, cov])


class FitCurvesMaxValue(FitCurves):
    def do_fitting(self, xvals, yvals):
        # Find the peak value
        peak_index = yvals.index(max(yvals))
        return [[xvals[peak_index]], None]


# Return value from quadratic curve : y = a + b*x * c*(x**2)
def quadratic(x: float | NDArray, a: float, b: float, c: float) -> float | NDArray:
    return a + b * x + c * (x**2)


def fit_quadratic_curve(
    x_vals: list[float],
    y_vals: list[float],
    show_plot: bool = False,
    bounds: tuple[tuple, tuple] | None = None,
    default_bounds: float = 100.0,
):
    """
        Fit quadratic curve to a set of x,y values; return the fit parameters
        and covariance matrix

    :param data_results: dictionary containing data to be fitted
        { xval1:yval1, xval2:yval2 ...}
    :param show_plot: optional - show fit results and original data
        on plot (default = False)
    :param bounds:  optional tuple containing bounds for each parameter of the
        trial_quadratic function e.g. ( (0,0,0), (10,10,10))
    :param trial_quadratic : optional quadratic function to be used for fitting
        (default = 'quadratic')

    :return: fit params, covariance matrix
    """

    # print("Curve x : {}".format(x_vals))
    # print("Curve y : {}".format(y_vals))
    upper_bound = [default_bounds] * 3
    lower_bound = [-1.0 * default_bounds] * 3

    if bounds is not None:
        lower_bound = list(bounds[0])
        upper_bound = list(bounds[1])

    bounds = (tuple(lower_bound), tuple(upper_bound))
    param, cov = curve_fit(quadratic, x_vals, y_vals, bounds=bounds)
    print(f"Fit params (quadratic) : {param}")

    # change quadratic component of bounds to force linear fit
    lower_bound[-1] = -1e-12
    upper_bound[-1] = 1e-12
    bounds_linear_fit = (tuple(lower_bound), tuple(upper_bound))
    params_linear, cov = curve_fit(quadratic, x_vals, y_vals, bounds=bounds_linear_fit)
    print(f"Fit params (linear) : {params_linear}")

    if show_plot:
        # Make arrays with x-y coords of fitted function profile
        xvals_func = np.arange(min(x_vals), max(x_vals), 0.05)
        yvals_func = quadratic(xvals_func, param[0], param[1], param[2])

        plt.figure("Curve fit").clear()
        plt.plot(x_vals, y_vals, label="values", marker="x")

        plt.plot(xvals_func, yvals_func, label="best fit (quadratic)")

        yvals_linear = quadratic(xvals_func, *params_linear)
        plt.plot(xvals_func, yvals_linear, label="best fit (linear)")

        plt.legend()
        plt.show()

    return param, cov


def trial_gaussian(x: float|NDArray, a: float, b: float, c: float) -> float:
    return a * np.exp(-(((x - c) * b) ** 2))


def gaussian_bounds_provider(
    xvals: list[float], yvals: list[float], peak_fit_fraction: float = 0.1
) -> tuple[tuple[float], tuple[float]]:
    bounds_a = 0, max(yvals) + 0.1
    bounds_b = 0, 10000

    # compute approximate centre position from weighted x position :
    weighted_centre = sum(np.array(xvals) * np.array(yvals)) / sum(yvals)
    # set the centre range 10% either side of the peak position
    c_range = max(xvals) - min(xvals)
    centre_range = c_range * peak_fit_fraction
    bounds_c = weighted_centre - centre_range, weighted_centre + centre_range

    return (bounds_a[0], bounds_b[0], bounds_c[0]), (
        bounds_a[1],
        bounds_b[1],
        bounds_c[1],
    )


def normalise_xvals(xvals: list[float], yvals: list[float]) -> tuple[list[float]]:
    return [x - xvals[0] for x in xvals], yvals


def max_value(x: list[float], height: float, peak_position: float, delta=0.01) -> list[float]:
    delta = (max(x) - min(x)) / 1000
    return [height if abs(xval - peak_position) < delta else 0.0 for xval in x]


def max_value_bounds(xvals, yvals):
    return (min(yvals), min(xvals)), (max(yvals), max(xvals))