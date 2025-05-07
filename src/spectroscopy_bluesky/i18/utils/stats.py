import numpy as np


def normalise_xvals(xvals, yvals):
    return [x - xvals[0] for x in xvals], yvals


def max_value(x, height, peak_position, delta=0.01):
    delta = (max(x) - min(x)) / 1000
    return [height if abs(xval - peak_position) < delta else 0.0 for xval in x]


def max_value_bounds(xvals, yvals):
    return (min(yvals), min(xvals)), (max(yvals), max(xvals))


def quadratic(x, a, b, c) -> float:
    return a + b * x + c * (x**2)

def trial_gaussian(x, a, b, c):
    return a * np.exp(-(((x - c) * b) ** 2))


def bounds_provider(xvals, yvals):
    bounds_a = 0, max(yvals) + 0.1
    bounds_b = 0, 10000

    # compute approximate centre position from weighted x position :
    weighted_centre = sum(np.array(xvals) * np.array(yvals)) / sum(yvals)
    # set the centre range 10% either side of the peak position
    c_range = max(xvals) - min(xvals)
    centre_range = c_range * 0.1
    bounds_c = weighted_centre - centre_range, weighted_centre + centre_range

    return (bounds_a[0], bounds_b[0], bounds_c[0]), (
        bounds_a[1],
        bounds_b[1],
        bounds_c[1],
    )
