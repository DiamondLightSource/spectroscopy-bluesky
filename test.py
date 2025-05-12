from bluesky import RunEngine
from dodal.beamlines.i20_1 import turbo_slit, panda
from spectroscopy_bluesky.i20_1.plans.direct_turbo_slit_movement import fly_scan_ts, fly_sweep, fly_sweep_both_ways
from ophyd_async.plan_stubs import ensure_connected


t = turbo_slit()
p = panda()

RE = RunEngine()
RE(ensure_connected(t,p))
RE(fly_sweep_both_ways(start=0, stop=10, num=11, duration=1.0,panda=p, number_of_sweeps=3))
