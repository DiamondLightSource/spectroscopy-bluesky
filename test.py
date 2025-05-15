from bluesky import RunEngine
from dodal.beamlines.i20_1 import turbo_slit, panda
from spectroscopy_bluesky.i20_1.plans.direct_turbo_slit_movement import trajectory_fly_scan, fly_scan_ts
from ophyd_async.plan_stubs import ensure_connected


t = turbo_slit()
p = panda()

RE = RunEngine()
RE(ensure_connected(t,p))
RE(trajectory_fly_scan(start=-30, stop=30, num=100, duration=0.01,panda=p, number_of_sweeps=30))
# RE(fly_scan_ts(start=0, stop=10, num=11, duration=0.01,panda=p))
