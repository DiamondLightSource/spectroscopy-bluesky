# /// script
# requires-python = ">=3.10"
# dependencies = [
#    "event-model",
#    "marimo",
#    "pydantic",
# ]
# ///

# Copyright 2024 Marimo. All rights reserved.

import event_model
import marimo
import pydantic

__generated_with = "0.13.8"
app = marimo.App()


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""# Welcome to marimo! 🌊🍃""")
    mo.md(r"""
        # Curve Fitting with Marimo
        This notebook demonstrates how to perform curve fitting using 
        the `curve_fit` function from `scipy.optimize`.
        """)

    class RmqConfig(pydantic.BaseModel):
        rmq_host: str = "rmq"
        rmq_port: int = 61613
        rmq_user: str = "user"
        rmq_password: str = "password"
        rmq_channel: str = "/topic/public.worker.event"

    class CallArgs(pydantic.BaseModel):
        rmq_config: RmqConfig = RmqConfig()
        # todo add the rest of the args

    return


@app.cell
def _(mo):
    args = mo.cli_args()
    print(args)
    print("the above were args, hello world!")
    # todo validatre the args against the pydantic model
    print("Curve fitting not yet implemented")
    return


@app.cell
def _():
    import stomp

    CHANNEL = "/topic/public.worker.event"

    class STOMPListener(stomp.PrintingListener):
        def on_error(self, frame):
            print(f"Error: {frame.body}")

        # todo need to parse the message
        # todo start streaming an hdf5 file if needed https://docs.h5py.org/en/latest/quick.html
        def on_message(self, frame):
            message = frame.body
            print(f"Received message: {message}")
            # todo parse the message into event model represeantations

    def start_stomp_connection():
        conn = stomp.Connection([("rmq", 61613)], auto_content_length=False)
        conn.set_listener("", STOMPListener())
        try:
            conn.connect("user", "password", wait=True)
        except stomp.exception.ConnectFailedException as e:  # type: ignore
            print(
                f"Connection failed. Please check your credentials and server address., error: {e}"
            )
            return None
        return conn

    conn = start_stomp_connection()
    if conn is None:
        print("Failed to connect to STOMP server.")
    else:
        conn.subscribe(CHANNEL, id=1, ack="auto")
        conn.disconnect()


@app.cell
def _():
    from scipy.optimize import Bounds, curve_fit

    from spectroscopy_bluesky.i18.utils.stats import trial_gaussian

    events: list[event_model.Event] = []

    # todo outer state
    motor_names = []
    main_detector_name = ""
    shape = 2, 100

    def on_event(event: event_model.Event):
        # process the event
        print(f"Processing event: {event}")
        events.append(event)
        if event.get("name") == "start":
            # start the curve fitting process
            print("Starting curve fitting process...")
            shape = event.get("shape") or [event.get("num_points", 0)]
            # todo persist the shape
            print(f"Shape: {shape}")
            motor_names = event.get("motors", [])
            main_detector_name = event.get("detectors", [])[0]

    results = []

    def fit():
        xvals = [e["data"][motor_names[-1]] for e in events]
        yvals = [e["data"][main_detector_name] for e in events]
        # normalize
        xvals = [x - xvals[0] for x in xvals]
        row_length = shape[-1]

        for i in range(0, len(events), shape[-1]):
            xvals_for_this_iter = xvals[i : i + row_length]
            yvals_for_this_iter = yvals[i : i + row_length]
            max_index = yvals_for_this_iter.index(max(yvals_for_this_iter))
            r = [xvals_for_this_iter[max_index], None]
            results.append(r)

    # todo return results back to the rmq

    outputs = []
    quadratic_bounds = Bounds(-100, 100)
    parameters_optimal, covariance, infodict, msg, found_flag = curve_fit(
        # lambda x, a: a * x + 5,
        trial_gaussian,
        [1, 2, 3],
        [4, 5, 6],
        bounds=quadratic_bounds,
    )
    print(f"Output: {outputs}")

    # for quad term near zero
    linear_bounds = Bounds(-1e-12, 1e-12)
    params_optimal_linear, covariance, infodict, msg, found_flag = curve_fit(
        # lambda x, a: a * x + 5,
        trial_gaussian,
        [1, 2, 3],
        [4, 5, 6],
        bounds=linear_bounds,
    )

    print(f"📈 Quadratic fit: {parameters_optimal}")
    print(f"📉 Linear fit:    {params_optimal_linear}")

    import matplotlib.pyplot as plt
    import numpy as np

    def plot_fit(
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

    return


if __name__ == "__main__":
    app.run()
