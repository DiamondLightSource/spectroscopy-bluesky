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
    import event_model
    import marimo
    import pydantic

    DEBUG_FLAG = True
    mo.md(r"""# Welcome to marimo! 🌊🍃""")
    mo.md(r"""
        # Curve Fitting with Marimo
        This notebook demonstrates how to perform curve fitting using 
        the `curve_fit` function from `scipy.optimize`.
        """)

    args = mo.cli_args()
    print(args)
    print("the above were args, hello world!")

    ### data_encoder.py
    import base64
    from io import BytesIO

    import pandas as pd
    from pydantic import BaseModel

    class CallArgs(BaseModel):
        shape: tuple[int, int]
        data: str

    def debug_dataframe(df, name="DataFrame"):
        """
        Print diagnostics for a pandas DataFrame.
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

    def dataframe_to_base64_csv(df: pd.DataFrame) -> str:
        buffer = BytesIO()
        df.to_csv(buffer, index=False)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def parse_debug_table(file_path: str) -> pd.DataFrame:
        with open(file_path, "r") as f:
            lines = f.readlines()

        # Remove comment and units lines
        data_lines = [
            line.strip()
            for line in lines
            if not line.startswith("#") and not line.startswith("Units")
        ]

        # Use whitespace to split columns
        df = pd.read_csv(
            BytesIO("\n".join(data_lines).encode()),
            delim_whitespace=True,
            names=["bragg", "idgap"],
        )
        return df

    call_args = CallArgs.model_validate(args)
    data = call_args.shape
    if DEBUG_FLAG:
        # load python txt as csv
        mock_dataframe = parse_debug_table("./debug_output_table.txt")
        data = dataframe_to_base64_csv(mock_dataframe)
    assert isinstance(data, str), 'args["data"] must be a string'
    df = base64_csv_to_dataframe(data)
    debug_dataframe(df, name="Decoded DataFrame")

    print("Curve fitting not yet implemented further")
    return (call_args,)


@app.cell
def _(linear_stuff, main_detector_name, motor_names, quad_stuff):
    from typing import TypedDict

    import numpy as np
    from scipy.optimize import Bounds, curve_fit

    class HarmonicData(BaseModel):
        harmonic: int
        x: list[float]
        y: list[float]

    class AllHarmonics(BaseModel):
        harmonics: list[HarmonicData]
    # todo debug this with the mock data

    # first stage is gaussian fitting
    # NOTE: if functions used much, best if published as a pypi package
    def trial_gaussian(x, a, b, c):
        return a * np.exp(-(((x - c) * b) ** 2))

    results = []
    bounds = Bounds([-100, -10, -100], [100, 10, 100])

    # todo need to create mock events I think those csv are the output, not events
    events = []
    xvals = [e["data"][motor_names[-1]] for e in events]
    yvals = [e["data"][main_detector_name] for e in events]
    # normalize
    xvals = [x - xvals[0] for x in xvals]
    row_length = call_args.shape[0]
    cols = call_args.shape[1]

    for i in range(0, len(events), cols):
        xvals_for_this_iter = xvals[i : i + row_length]
        yvals_for_this_iter = yvals[i : i + row_length]
        max_index = yvals_for_this_iter.index(max(yvals_for_this_iter))
        r = [xvals_for_this_iter[max_index], None]
        results.append(r)
        # what is the relationship between the scipy based do_fitting and the other fitting

        # quadratic_bounds = Bounds(-100, 100)
        # todo I need to actually get the values right
        parameters_optimal_quad, covariance_quad = curve_fit(
            trial_gaussian,
            np.array([1, 2, 3]),
            np.array([4, 5, 6]),
            p0=[1, 1, 1],
            bounds=bounds,
        )

        # for quad term near zero
        # linear_bounds = Bounds(-1e-12, 1e-12)
        params_optimal_linear, covariance_linear = curve_fit(
            trial_gaussian,
            [1, 2, 3],
            [4, 5, 6],
            # bounds=linear_bounds,
            bounds=bounds,
        )

        print(f"📈 Quadratic fit: {parameters_optimal_quad}")
        print(f"📉 Linear fit:    {params_optimal_linear}")
        results.append([parameters_optimal_quad, covariance_quad])
        # NOTE: parameters are always a tuple of 3 numbers

    # todo return results back to the rmq - need to choose what format to use
    serialized_results = results

    import matplotlib.pyplot as plt
    import numpy as np

    def plot_results(
        linear_stuf: tuple[float, float, float],
        quad_stuf: tuple[float, float, float],
        raw_data: list[tuple[float, float]],
    ):
        """
        tuples of parameters and covariance
        """
        plt.figure("Curve fit")
        plt.figure("Curve Fit").clear()
        plt.plot(raw_data[0], raw_data[1], "x", label="Data")
        plt.plot(quad_stuff, quad_stuff, "-", label="Quadratic Fit")
        plt.plot(linear_stuff, linear_stuff, "--", label="Linear Fit")
        plt.legend()
        plt.xlabel("x")
        plt.ylabel("y")
        plt.title("Curve Fitting")
        plt.grid(True)
        plt.savefig(
            "/tmp/plot.png"
        )  # todo this should conform to the expected png / whatever extension is expected
        # https://diamondlightsource.github.io/workflows/docs/how-tos/create-artifacts/

    # todo need to get the raw data or just xs and ys
    return (plot_results,)


if __name__ == "__main__":
    app.run()
