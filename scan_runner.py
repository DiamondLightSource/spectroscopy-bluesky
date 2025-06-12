#!./venv/bin/python

import typer
from bluesky import RunEngine
from dodal.beamlines.i20_1 import panda, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.i20_1.plans.direct_turbo_slit_movement import (
    fly_sweep_both_ways,
    seq_table_test,
    trajectory_fly_scan,
)

# Typer definitions
app = typer.Typer(help="CLI Interface for running scans")

_start = typer.Option(help="Starting position of the scan", default=0.0)

_stop = typer.Option(help="Ending position of the scan", default=10.0)

_num = typer.Option(help="Number of points of the scan", default=100)

_duration = typer.Option(
    help="Duration of the acquisition starting on the rising edge of a trigger", default=0.01
)

_sweeps = typer.Option(help="Number of sweeps", default=1)

# Create the PMAC and Panda objects making sure they're connected
t = turbo_slit()
p = panda()
RE = RunEngine()
RE(ensure_connected(t, p))


@app.command()
def fly_scan_seq_table(
    start: float = _start,
    stop: float = _stop,
    num: int = _num,
    duration: float = _duration,
    sweeps: int = _sweeps,
):
    """
    Run a trajectory scan using the sequencer table as a trigger source and a trajectory on the PMAC.\n
    Currently only supports one sequencer table with 4096 points.\n
    This scan requires the `seq_table` design to be loaded in the Panda.
    """
    RE(
        seq_table_test(
            start=start,
            stop=stop,
            num=num,
            duration=duration,
            panda=p,
            number_of_sweeps=sweeps,
        )
    )


@app.command()
def fly_scan_trajectory(
    start: float = _start,
    stop: float = _stop,
    num: int = _num,
    duration: float = _duration,
    sweeps: int = _sweeps,
):
    """
    Run a trajectory scan using the PCOMP block as trigger source and a trajectory on the PMAC.\n
    PCOMP sends a trigger based on the starting position and evenly spaces them.\n
    This scan requires the `pcomp_auto_reset` design to be loaded in the Panda.
    """
    RE(
        trajectory_fly_scan(
            start=start,
            stop=stop,
            num=num,
            duration=duration,
            panda=p,
            number_of_sweeps=sweeps,
        )
    )


@app.command()
def fly_scan(
    start: float = _start,
    stop: float = _stop,
    num: int = _num,
    duration: float = _duration,
    sweeps: int = _sweeps,
):
    """
    Run a scan using the PCOMP block as trigger source.\n
    This scan does a `kick off` of the motor at each sweep.\n
    This scan requires the `pcomp_auto_reset` design to be loaded in the Panda.
    """
    RE(
        fly_sweep_both_ways(
            start=start,
            stop=stop,
            num=num,
            duration=duration,
            panda=p,
            number_of_sweeps=sweeps,
        )
    )


if __name__ == "__main__":
    app()
