from bluesky import RunEngine
from dodal.beamlines.i20_1 import turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.i20_1.plans.direct_turbo_slit_movement import (
    panda,
)

RE = RunEngine()
RE(ensure_connected(turbo_slit(),panda))
