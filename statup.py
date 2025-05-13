from bluesky import RunEngine
from dodal.beamlines.i20_1 import turbo_slit, panda
from spectroscopy_bluesky.i20_1.plans.direct_turbo_slit_movement import (
    fly_scan_ts,
    fly_sweep,
    fly_sweep_both_ways,
)
from ophyd_async.plan_stubs import ensure_connected


RE = RunEngine()
RE(ensure_connected(turbo_slit(), panda()))
