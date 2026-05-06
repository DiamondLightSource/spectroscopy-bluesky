from pathlib import PurePath

from bluesky import RunEngine
from dodal.beamlines.p51 import panda1, panda2, turbo_slit_x
from dodal.utils import BeamlinePrefix, get_beamline_name
from ophyd_async.core import PathProvider, StaticFilenameProvider, StaticPathProvider
from ophyd_async.fastcs.xspress import XspressDetector
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans.common import restore_panda_settings

BL = get_beamline_name("P51")
PREFIX = BeamlinePrefix(BL)


def static_panda_path_provider1() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("panda_seq"),
        PurePath("/dls/p51/data/2026/cm44254-2/tmp/"),
    )


def static_panda_path_provider2() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("panda_fast"),
        PurePath("/dls/p51/data/2026/cm44254-2/tmp/"),
    )


def static_xsp_path_provider() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("xsp"),
        PurePath("/dls/p51/data/2026/cm44254-2/tmp/"),
    )


RE = RunEngine()
p_encoder = panda1(static_panda_path_provider1())
p_debug = panda2(static_panda_path_provider2())
xsp = XspressDetector(
    prefix="BL51P-EA-XSP-01:",
    path_provider=static_xsp_path_provider(),
    name="xspress",
)

m = turbo_slit_x()
RE(ensure_connected(m, p_encoder, p_debug, xsp))
restore_panda_settings([p_encoder, p_debug], False, True, False)
