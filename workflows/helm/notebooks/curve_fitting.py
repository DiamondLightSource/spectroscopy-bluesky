# /// script
# requires-python = ">=3.10"
# dependencies = [
#    "event-model==1.22.3",
#    "marimo",
#    "pydantic==2.11.4",
#    "stomp.py",
#    "scipy==1.15.3",
#    "matplotlib==3.10.3",
#    "numpy==2.2.6",
# ]
# ///

# Copyright 2024 Marimo. All rights reserved.

import marimo

__generated_with = "0.13.9"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    import ast

    mo.md(r"""# Welcome to marimo! 🌊🍃""")
    mo.md(r"""
        # Curve Fitting with Marimo
        This notebook demonstrates how to perform curve fitting using 
        the `curve_fit` function from `scipy.optimize`.
        """)

    args = mo.cli_args()
    print(
        f"Starting the curve fitting workflow for spectroscopy using arguments: {args}"
    )

    import base64
    from io import BytesIO

    import pandas as pd
    from pydantic import BaseModel

    class CallArgs(BaseModel):
        shape: tuple[int, int]
        data: str

    def debug_dataframe(df, name="DataFrame"):
        """
        UTILITY: Print diagnostics for a pandas DataFrame.
        """
        print(f"--- {name} diagnostics ---")
        print(f"Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        print("Dtypes:")
        print(df.dtypes)
        print("Head:")
        print(df.head())
        print("Info:")
        df.info()
        print("-" * 40)

    def base64_csv_to_dataframe(b64_string: str) -> pd.DataFrame:
        decoded = base64.b64decode(b64_string)
        return pd.read_csv(BytesIO(decoded))

    raw_shape = args.get("shape")
    new_args = args.to_dict()
    if isinstance(raw_shape, str):
        shape_value = ast.literal_eval(raw_shape)
    else:
        shape_value = raw_shape
    new_args["shape"] = shape_value
    call_args = CallArgs.model_validate(new_args)
    data = call_args.data
    assert isinstance(data, str), 'args["data"] must be a string'
    df = base64_csv_to_dataframe(data)
    debug_dataframe(df, name="Decoded DataFrame")

    print("Curve fitting not yet implemented further")
    return (call_args, df)


@app.cell
def _(df, call_args, debug_dataframe, pd):
    import numpy as np
    from scipy.optimize import curve_fit

    def trial_gaussian(x, a, b, c):
        return a * np.exp(-(((x - c) * b) ** 2))

    def fit_peaks_by_bragg(df: pd.DataFrame) -> pd.DataFrame:
        results = []
        for bragg_angle, group in df.groupby("x"):
            x = group["x"].values
            y = group["y"].values
            # Initial guess: amplitude=max(y), width=0.1, center=mean(x)
            p0 = [y.max(), 0.1, x[np.argmax(y)]]
            try:
                popt, _ = curve_fit(trial_gaussian, x, y, p0=p0)
                peak_x = popt[2]
            except Exception as e:
                peak_x = np.nan  # or handle as needed
            results.append({"bragg_angle": bragg_angle, "x": peak_x})
        return pd.DataFrame(results)

    fitted_peaks = fit_peaks_by_bragg(df)
    debug_dataframe(fitted_peaks)


@app.cell
def _(fitted_peaks, debug_dataframe, pd, curve_fit, np):
    import matplotlib.pyplot as plt

    # Inverse quadratic model: y = a / (x - b)**2 + c
    def inverse_quadratic(x, a, b, c):
        return a / (x - b) ** 2 + c

    # Prepare data for fitting
    xdata = fitted_peaks["bragg_angle"].values
    ydata = fitted_peaks["x"].values  # gap values

    # Reasonable initial guess and bounds
    p0 = [1.0, 0.0, 0.0]
    bounds = ([0, -100, -100], [1e6, 100, 100])

    # Fit the inverse quadratic
    try:
        popt, pcov = curve_fit(inverse_quadratic, xdata, ydata, p0=p0, bounds=bounds)
    except Exception as e:
        print(f"Fit failed: {e}")
        popt = [np.nan, np.nan, np.nan]

    # Plot the fit and data
    plt.figure(figsize=(8, 5))
    plt.scatter(xdata, ydata, label="Peak gap (from Gaussian fit)", color="blue")
    xfit = np.linspace(xdata.min(), xdata.max(), 500)
    yfit = inverse_quadratic(xfit, *popt)
    plt.plot(xfit, yfit, label="Inverse Quadratic Fit", color="red")
    plt.xlabel("Bragg Angle")
    plt.ylabel("Gap (x at peak)")
    plt.title("Curve Fitting")
    plt.legend()
    plt.grid(True)
    plt.savefig("/tmp/plot.png")  # Interpolate new values every 0.1 in Bragg angle
    x_interp = np.arange(xdata.min(), xdata.max() + 0.1, 0.1)
    y_interp = inverse_quadratic(x_interp, *popt)
    interp_df = pd.DataFrame({"bragg_angle": x_interp, "gap": y_interp})
    interp_df.to_csv("/tmp/interpolated_gap_vs_bragg.csv", index=False)

    debug_dataframe(interp_df, name="Interpolated Gap vs Bragg Angle")
    print(
        "Saved plot to /tmp/inverse_quadratic_fit.png and CSV to /tmp/interpolated_gap_vs_bragg.csv"
    )
    # todo this should conform to the expected png / whatever extension is expected
    # https://diamondlightsource.github.io/workflows/docs/how-tos/create-artifacts/

    return interp_df


if __name__ == "__main__":
    app.run()
