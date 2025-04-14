def normalise_xvals(xvals, yvals):
    return [x - xvals[0] for x in xvals], yvals


def max_value(x, height, peak_position, delta=0.01):
    delta = (max(x) - min(x)) / 1000
    return [height if abs(xval - peak_position) < delta else 0.0 for xval in x]


def max_value_bounds(xvals, yvals):
    return (min(yvals), min(xvals)), (max(yvals), max(xvals))


def quadratic(x, a, b, c) -> float:
    return a + b * x + c * (x**2)
