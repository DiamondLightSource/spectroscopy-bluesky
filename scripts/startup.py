from bluesky import RunEngine
from dodal.beamlines.p51 import panda, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans.direct_turbo_slit_movement import (
    seq_non_linear,  # noqa: F401
    seq_table,  # noqa: F401
)

RE = RunEngine()
p = panda()
RE(ensure_connected(turbo_slit(), p))
