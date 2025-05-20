from bluesky import RunEngine
from dodal.beamlines.i20_1 import panda, turbo_slit
from ophyd_async.plan_stubs import ensure_connected

RE = RunEngine()
RE(ensure_connected(turbo_slit(), panda()))
