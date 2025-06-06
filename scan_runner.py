#!./venv/bin/python

import argparse

from bluesky import RunEngine
from dodal.beamlines.i20_1 import panda, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.i20_1.plans.direct_turbo_slit_movement import (
    fly_sweep_both_ways,
    seq_table_test,
    trajectory_fly_scan,
)

parser = argparse.ArgumentParser(
    description="Interface for running example BlueSky scans"
)

parser.add_argument(
    "-s", "--start", help="Starting point of the scan", default=0, type=float
)

parser.add_argument(
    "-e", "--end", help="Final point of the scan", default=10, type=float
)

parser.add_argument(
    "-n", "--number", help="number of points in the scan", default=10, type=int
)


parser.add_argument(
    "-t", "--duration", help="How long to acquire for in s", default=0.01, type=float
)

parser.add_argument("-r", "--sweeps", help="How many sweeps to do", default=3, type=int)

parser.add_argument(
    "-x",
    "--scan",
    help="Which scan to run:\
                        \n1 = Fly scan with PMAC trajectory\
                        \n2 = Fly scan without trajectory\
                        \n3 = Fly scan with PMAC trajectory and sequencer table",
    default=3,
    type=int,
)

args = parser.parse_args()
start = args.start
stop = args.end
number = args.number
duration = args.duration
sweeps = args.sweeps

# Create the PMAC and Panda objects making sure they're connected
t = turbo_slit()
p = panda()
RE = RunEngine()
RE(ensure_connected(t, p))


match args.scan:
    case 1:
        RE(
            trajectory_fly_scan(
                start=start,
                stop=stop,
                num=number,
                duration=duration,
                panda=p,
                number_of_sweeps=sweeps,
            )
        )
    case 2:
        RE(
            fly_sweep_both_ways(
                start=start,
                stop=stop,
                num=number,
                duration=duration,
                panda=p,
                number_of_sweeps=sweeps,
            )
        )
    case 3:
        RE(
            seq_table_test(
                start=start,
                stop=stop,
                num=number,
                duration=duration,
                panda=p,
                number_of_sweeps=sweeps,
            )
        )
