from bluesky import RunEngine
from dodal.beamlines.p51 import panda, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans.direct_turbo_slit_movement import (
    trajectory_fly_scan,
)

t = turbo_slit()
p = panda()

RE = RunEngine()
RE(ensure_connected(t, p))
RE(
    trajectory_fly_scan(
        start=-30, stop=30, num=100, duration=0.01, panda=p, number_of_sweeps=30
    )
)
