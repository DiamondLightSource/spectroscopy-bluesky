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

__generated_with = "0.13.8"
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

    mo.md(r"""# Welcome to marimo! 🌊🍃""")
    mo.md(r"""
        # Curve Fitting with Marimo
        This notebook demonstrates how to perform curve fitting using 
        the `curve_fit` function from `scipy.optimize`.
        """)

    # this is read in the start document too - or descriptor document
    class CSVDataPayload(pydantic.BaseModel):
        records: list[dict[str, str]]

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
    # todo validatre the args against the pydantic model, maybe save to some output to confirm this happened
    print("Curve fitting not yet implemented")
    return


@app.cell
def _():
    import numpy as np
    from event_model import Event
    from scipy.optimize import Bounds, curve_fit

    # NOTE: if functions used much, best if published as a pypi package
    def trial_gaussian(x, a, b, c):
        return a * np.exp(-(((x - c) * b) ** 2))

    events: list[Event] = []

    motor_names = []
    main_detector_name = ""
    shape = 2, 100

    def on_event(event: Event):
        # process the event
        print(f"Processing event: {event}")
        events.append(event)
        if event.get("name") == "start":
            # start the curve fitting process
            print("Starting curve fitting process...")
            nonlocal shape
            shape = event.get("shape") or [event.get("num_points", 0)]
            print(f"Shape: {shape}")
            nonlocal motor_names
            nonlocal main_detector_name
            motor_names = event.get("motors", [])
            main_detector_name = event.get("detectors", [])[0]

    # todo consider a dataframe instead? maybe with polars https://pola.rs/
    results = []
    # https://docs.pydantic.dev/latest/examples/files/#csv-files
    import csv

    from pydantic import BaseModel, EmailStr, PositiveInt

    class Person(BaseModel):
        name: str
        age: PositiveInt
        email: EmailStr

    with open("people.csv") as f:
        reader = csv.DictReader(f)
        people = [Person.model_validate(row) for row in reader]

    print(people)
    # > [Person(name='John Doe', age=30, email='john@example.com'), Person(name='Jane Doe', age=25, email='jane@example.com')]

    bounds = Bounds([-100, -10, -100], [100, 10, 100])

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
        plt.savefig("/tmp/plot.png")
        # todo this should conform to the expected png / whatever extension is expected
        # https://diamondlightsource.github.io/workflows/docs/how-tos/create-artifacts/


@app.cell
def _():
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
    import stomp

    CHANNEL = "/topic/public.worker.event"

    class STOMPListener(stomp.PrintingListener):
        _conn: stomp.Connection | None

        def on_error(self, frame):
            print(f"Error: {frame.body}")

        def send_callback(self, data):
            """
            todo add the type
            """
            if self._conn is not None:
                self._conn.send(body=data, destination=CHANNEL)

        # todo need to parse the message
        # todo start streaming an hdf5 file if needed https://docs.h5py.org/en/latest/quick.html
        def on_message(self, frame):
            message = frame.body
            print(f"Received message: {message}")
            # todo parse the message into event model represeantations - use the stuff from above
            on_event(message, self.send_callback)

    def start_stomp_connection():
        # todo change this to use bluesky-stomp, like in blue-histogramming streaming context, using auth really - and this should be read from the params
        conn = stomp.Connection([("rmq", 61613)], auto_content_length=False)
        conn.set_listener("", STOMPListener())
        try:
            conn.connect("user", "password", wait=True)
        except stomp.exception.ConnectFailedException as e:  # type: ignore
            print(
                f"Connection failed. Please check your credentials and server address., error: {e}"  # noqa: E501
            )
            return None
        return conn

    conn = start_stomp_connection()
    if conn is None:
        print("Failed to connect to STOMP server.")
    else:
        conn.subscribe(CHANNEL, id=1, ack="auto")
        conn.disconnect()


if __name__ == "__main__":
    app.run()
