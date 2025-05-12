from collections.abc import Callable

import matplotlib.pyplot as plt
import numpy as np
from bluesky.callbacks.core import CollectThenCompute
from scipy.optimize import Bounds, curve_fit


class FitCurves(CollectThenCompute):
    """
    Callback listener that processes collected documents and
    fits detector data with curve :
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
        self.fit_function = None  # use trial_gaussian
        self.fit_bounds = None  # use bounds_provider
        self.results = []
        # A function to be applied to the x and y values before curve fitting
        # i.e. xvals_to_fit, yvals_to_fit = transform_function(xvals, yvals)
        self.transform_function = None  # use normalise_evals
        # Set a function to be used to compute the bounds to be used when fitting
        # The xvals and yvals are passed to the function, and it should
        self.bounds = None  # static bounds
        self.bounds_provider = (
            None  # function that provides bounds based on x and y values
        )

    def start(self, doc):
        self.results = []
        self.reset()
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
        return curve_fit(self.fit_function, xvals, yvals, bounds=bounds)

    def determine_scan_shape(self):
        # Extract information about scan shape from start document :
        return self._start_doc.get("shape") or [self._start_doc["num_points"]]  # type: ignore

    def extract_data(self):
        """Extract the x and y values (i.e. position of motor being moved and detector readout)
        from the event documents"""
        motor_names = self._start_doc["motors"]
        inner_loop_motor = motor_names[len(motor_names) - 1]
        det_name = self._start_doc["detectors"][0]

        xvals = [e["data"][inner_loop_motor] for e in self._events]
        yvals = [e["data"][det_name] for e in self._events]
        return xvals, yvals

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


def fit_quadratic_curve(
    data_results: dict[float, float],
    show_plot: bool = False,
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None,
    default_bounds: float = 100.0,
    trial_quadratic: Callable[..., float] = lambda x, a, b, c: a + b * x + c * x**2,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Fit a quadratic curve to x, y data.

    Args:
        data_results: Dictionary of {x: y} values.
        show_plot: Whether to show a plot of the fit.
        bounds: tuple of (lower_bounds, upper_bounds) for a, b, c.
        default_bounds: Used if bounds is not provided.
        trial_quadratic: Function to fit (default is a quadratic).

    Returns:
        tuple of (fit_parameters, covariance_matrix)
    """
    x_vals = list(data_results.keys())
    y_vals = list(data_results.values())

    if bounds is None:
        bounds = (
            (-default_bounds, -default_bounds, -default_bounds),
            (default_bounds, default_bounds, default_bounds),
        )
        # test_bounds = Bounds(-np.inf, np.inf, True)

    # Perform the bounded curve fit
    params_quadratic, cov_quadratic = curve_fit(
        trial_quadratic, x_vals, y_vals, bounds=bounds
    )

    # Perform an auxiliary linear fit (quadratic term nearly zero)
    linear_bounds = list(bounds[0]), list(bounds[1])
    linear_bounds[0][-1] = -1e-12
    linear_bounds[1][-1] = 1e-12

    params_linear, _ = curve_fit(
        trial_quadratic,
        x_vals,
        y_vals,
        bounds=(tuple(linear_bounds[0]), tuple(linear_bounds[1])),
    )

    print(f"📈 Quadratic fit: {params_quadratic}")
    print(f"📉 Linear fit:    {params_linear}")

    if show_plot:
        _plot_fit(x_vals, y_vals, params_quadratic, params_linear, trial_quadratic)

    return params_quadratic, cov_quadratic


def _plot_fit(
    x_vals: list[float],
    y_vals: list[float],
    params_quadratic,
    params_linear,
    model_func,
):
    x_range = np.linspace(min(x_vals), max(x_vals), 200)
    y_quad = model_func(x_range, *params_quadratic)
    y_lin = model_func(x_range, *params_linear)

    plt.figure("Curve Fit").clear()
    plt.plot(x_vals, y_vals, "x", label="Data")
    plt.plot(x_range, y_quad, "-", label="Quadratic Fit")
    plt.plot(x_range, y_lin, "--", label="Linear Fit")
    plt.legend()
    plt.xlabel("x")
    plt.ylabel("y")
    plt.title("Curve Fitting")
    plt.grid(True)
    plt.savefig("test_path")
    # plt.show() # we skip this
