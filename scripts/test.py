from bluesky import RunEngine
from dodal.beamlines.p51 import panda, path_provider, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans.turbo_slit_fly_scans import (
    trajectory_fly_scan,
)

t = turbo_slit()
p = panda(path_provider)

RE = RunEngine()
RE(ensure_connected(t, p))
RE(trajectory_fly_scan(start=-30, stop=30, num=100, duration=0.01, panda=p))
