from pathlib import PurePath

from bluesky.run_engine import RunEngine
from dodal.beamlines.p51 import (
    panda1,
    panda2,
    turbo_slit_pmac,
    turbo_slit_x,
    # eurotherm2k
)

# from dodal.devices.eurotherm import EurothermGeneral
from ophyd_async.core import PathProvider, StaticFilenameProvider, StaticPathProvider
from ophyd_async.fastcs.xspress import XspressDetector
from ophyd_async.plan_stubs import ensure_connected


def static_panda_path_provider_main() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("panda_acquisition.h5"),
        PurePath("/dls/p51/data/2026/cm44254-4/tmp/"),
    )


def static_panda_path_provider_debug() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("panda_debug.h5"),
        PurePath("/dls/p51/data/2026/cm44254-4/tmp/"),
    )


def static_xsp_path_provider() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("xsp3xm2.h5"),
        PurePath("/dls/p51/data/2026/cm44254-4/tmp/"),
    )


RE = RunEngine()
path_provider_main = static_panda_path_provider_main()
path_provider_debug = static_panda_path_provider_debug()

p = panda1(path_provider_main)
p2 = panda2(path_provider_debug)
ts = turbo_slit_x()
pmac = turbo_slit_pmac(ts)
# eurotherm = eurotherm2k()
xsp = XspressDetector(
    prefix="BL51P-EA-XSP-01:",
    path_provider=static_xsp_path_provider(),
    name="xsp3m2",
)
RE(ensure_connected(p, p2, ts, pmac, xsp))
