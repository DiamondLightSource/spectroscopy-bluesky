import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from bluesky.utils import MsgGenerator
from ophyd_async.core import (
    DetectorTrigger,
)
from ophyd_async.fastcs.xspress import XspressDetector, XspressTriggerInfo
from ophyd_async.plan_stubs import ensure_connected


def xsp_scan(
    xspress: XspressDetector,
    num_frames: int = 10,
    time_per_frame: float = 1,
    chunk: int | None = None,
) -> MsgGenerator:
    yield from ensure_connected(xspress)

    @bpp.run_decorator()
    @bpp.stage_decorator([xspress])
    def inner_plan():
        xsp_trigger = XspressTriggerInfo(
            number_of_events=num_frames,
            trigger=DetectorTrigger.INTERNAL,
            livetime=time_per_frame,
            chunk=int(1 / time_per_frame) if chunk is None else chunk,
        )

        yield from bps.prepare(xspress, xsp_trigger, wait=True)
        yield from bps.kickoff(xspress, wait=True)
        yield from bps.complete_all(xspress, wait=True)

    yield from inner_plan()
