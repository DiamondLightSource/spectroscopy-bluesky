from bluesky import RunEngine
from dodal.beamlines.p51 import panda, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans.seq_table_scans import (
    seq_non_linear,  # noqa: F401
    seq_table,  # noqa: F401
)

RE = RunEngine()
p = panda()
RE(ensure_connected(turbo_slit(), p))
