from bluesky.callbacks.core import CollectThenCompute
from scipy.optimize import curve_fit


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
        self.fit_function = None
        self.fit_bounds = None
        self.results = []
        self.transform_function = None
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
        else:
            return curve_fit(self.fit_function, xvals, yvals, bounds=bounds)

    def determine_scan_shape(self):
        # Extract information about scan shape from start document :
        scan_shape = self._start_doc.get("shape")
        if scan_shape is None:
            scan_shape = [self._start_doc["num_points"]]
        return scan_shape

    def extract_data(self):
        """Extract the x and y values (i.e. position of motor being moved and detector readout)
        from the event documents"""
        motor_names = self._start_doc["motors"]
        inner_loop_motor = motor_names[len(motor_names) - 1]
        det_name = self._start_doc["detectors"][0]

        xvals = [e["data"][inner_loop_motor] for e in self._events]
        yvals = [e["data"][det_name] for e in self._events]
        return xvals, yvals

    def set_transform_function(self, transform_function):
        """
            A function to be applied to the x and y values before curve fitting
            i.e. xvals_to_fit, yvals_to_fit = transform_function(xvals, yvals)

        :param transform_function: takes the xvalues, yvalues and returns new set of values
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
