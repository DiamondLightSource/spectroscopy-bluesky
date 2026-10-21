import math as mt

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.utils import MsgGenerator
from dodal.beamlines.p51 import turbo_slit_pmac
from ophyd_async.core import DetectorTrigger, TriggerInfo
from ophyd_async.epics.motor import Motor
from ophyd_async.epics.pmac import PmacScanInfo, PmacTrajectoryFlyableLogic
from ophyd_async.fastcs.panda import (
    HDFPanda,
    SeqTableInfo,
    StaticSeqTableFlyableLogic,
)
from ophyd_async.fastcs.xspress import XspressDetector
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Fly, Line

from spectroscopy_bluesky.p51.plans.sequence_table import (
    SeqTableBuilder,
)

from .common import (
    get_encoder_counts,
)


def xsp_scan(
    xspress: XspressDetector,
    num_frames: int = 10,
    time_per_frame: float = 1,
) -> MsgGenerator:
    """Scan using only Xspress detector.

    Args:
        xspress (XspressDetector): FastCS-Xspress object to use in the scan.
        num_frames (int): number of frames to acquire.

        time_per_frame (float): acquisition time of each frame in seconds.
    Returns:
        Callable[[], MsgGenerator]: _description_

    Yields:
        Iterator[Callable[[], MsgGenerator]]: _description_

    """
    yield from ensure_connected(xspress)

    @bpp.run_decorator()
    @bpp.stage_decorator([xspress])
    def inner_plan():
        xsp_trigger = TriggerInfo(
            number_of_events=num_frames,
            trigger=DetectorTrigger.INTERNAL,
            livetime=time_per_frame,
        )

        yield from bps.prepare(xspress, xsp_trigger, wait=True)
        yield from bps.kickoff(xspress, wait=True)
        yield from bps.complete_all(xspress, wait=True)

    yield from inner_plan()


def xsp_motor_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor,
    panda: HDFPanda,
    detector: XspressDetector,
    num_trajectory_points: int = 10,
    number_of_sweeps: int = 2,
):
    pmac = turbo_slit_pmac(motor)
    yield from ensure_connected(pmac, motor, panda, detector)
    seqtable = StaticSeqTableFlyableLogic(panda.seq[1])
    seqtable_flyer = seqtable.with_device()
    time_per_traj_point = time_per_sweep / num_trajectory_points
    spec = Fly(
        time_per_traj_point
        @ (number_of_sweeps * ~Line(motor, start, stop, num_trajectory_points))
    )
    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)
    # add points to capture positions on the reverse sweep
    if number_of_sweeps > 1:
        num_seqtable_repeats = mt.ceil(number_of_sweeps / 2)
        num_captures = capture_positions.size
        positions = np.zeros(2 * num_captures)
        positions[0:num_captures] = capture_positions
        positions[num_captures : num_captures * 2] = np.flip(capture_positions)
    else:
        positions = capture_positions
        num_seqtable_repeats = 1

    seqTable_builder = SeqTableBuilder()
    seqTable_builder.convert_to_encoder = get_encoder_counts
    seqTable_builder.add_positions(positions, time1=1, outa1=True, time2=1, outa2=False)

    seqTableInfo = SeqTableInfo(
        sequence_table=seqTable_builder.get_seq_table(),
        repeats=num_seqtable_repeats,
        prescale_as_us=1,
    )
    pandaHdfInfo = TriggerInfo(
        number_of_events=0,
        trigger=DetectorTrigger.EXTERNAL_LEVEL,
        livetime=time_per_traj_point,
        deadtime=1e-5,
    )
    scanInfo = PmacScanInfo(spec=spec, ramp_time=None, turnaround_time=None)
    xsp_trigger = TriggerInfo(
        number_of_events=capture_positions.size * number_of_sweeps,
        trigger=DetectorTrigger.EXTERNAL_EDGE,
        livetime=time_per_traj_point,
        deadtime=7e-5,
    )

    pmac_trajectory = PmacTrajectoryFlyableLogic(pmac)
    pmac_trajectory_flyer = pmac_trajectory.with_device()

    @bpp.run_decorator()
    @bpp.stage_decorator([panda, detector])
    def inner_plan():
        # Prepare pmac with the trajectory
        yield from bps.prepare(pmac_trajectory_flyer, scanInfo, wait=True)

        # prepare sequencer table
        yield from bps.prepare(seqtable_flyer, seqTableInfo, wait=True)
        yield from bps.prepare(panda, pandaHdfInfo, wait=True)
        yield from bps.prepare(detector, xsp_trigger, wait=True)

        # kickoff devices waiting for all of them
        yield from bps.kickoff(panda, wait=True)
        yield from bps.kickoff(seqtable_flyer, wait=True)
        yield from bps.kickoff(detector, wait=True)
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        yield from bps.complete_all(
            pmac_trajectory_flyer, detector, panda, seqtable_flyer, wait=True
        )

    yield from inner_plan()
