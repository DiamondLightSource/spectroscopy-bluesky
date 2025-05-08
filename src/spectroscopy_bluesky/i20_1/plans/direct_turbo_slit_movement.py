import math as mt
from os import TMP_MAX

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.plans import count
from bluesky.protocols import Movable, Readable
from bluesky.utils import MsgGenerator

# from dodal.beamlines.i20_1 import panda, turbo_slit
from dodal.beamlines.i20_1 import turbo_slit
from dodal.common.coordination import inject
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator
from ophyd_async.core import (
    DetectorTrigger,
    StandardFlyer,
    TriggerInfo,
)
from ophyd_async.epics.motor import FlyMotorInfo
from ophyd_async.fastcs.panda import (
    HDFPanda,
    PandaPcompDirection,
    PcompInfo,
    StaticPcompTriggerLogic,
)


def fly_scan_ts(
    start: int,
    stop: int,
    num: int,
    duration: float,
    panda: HDFPanda = inject("panda"),  # noqa: B008
) -> MsgGenerator:
    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        motor = turbo_slit().xfine
        width = (stop - start) / (num - 1)
        start_pos = start - (width / 2)
        stop_pos = stop + (width / 2)
        MRES = -1 / 10000
        motor_info = FlyMotorInfo(
            start_position=start_pos,
            end_position=stop_pos,
            time_for_move=num * duration,
        )
        panda_pcomp_info = PcompInfo(
            start_postion=mt.ceil(start_pos / (MRES)),
            pulse_width=1,
            rising_edge_step=mt.ceil(abs(width / MRES)),
            number_of_pulses=num,
            direction=PandaPcompDirection.POSITIVE
            if width / MRES > 0
            else PandaPcompDirection.NEGATIVE,
        )

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.CONSTANT_GATE,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(motor, motor_info)
        yield from bps.prepare(panda, panda_hdf_info)
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)
        yield from bps.kickoff(panda)
        yield from bps.kickoff(panda_pcomp, wait=True)
        yield from bps.kickoff(motor, wait=True)
        yield from bps.complete_all(motor, panda_pcomp, panda, wait=True)

    yield from inner_plan()


def fly_sweep(
    start: int,
    stop: int,
    num: int,
    duration: float,
    panda: HDFPanda = inject("panda"),  # noqa: B008
    number_of_sweeps: int = 5,
) -> MsgGenerator:
    """

    just just make one long file - that is stage and unstage only once

    """
    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    MOTOR_RESOLUTION = -1 / 10000

    def inner_squared_plan(start: float | int, stop: float | int):
        motor = turbo_slit().xfine
        width = (stop - start) / (num - 1)
        start_pos = start - (width / 2)
        stop_pos = stop + (width / 2)
        motor_info = FlyMotorInfo(
            start_position=start_pos,
            end_position=stop_pos,
            time_for_move=num * duration,
        )
        direction_of_sweep = (
            PandaPcompDirection.POSITIVE
            if width / MOTOR_RESOLUTION > 0
            else PandaPcompDirection.NEGATIVE
        )

        panda_pcomp_info = PcompInfo(
            start_postion=mt.ceil(start_pos / (MOTOR_RESOLUTION)),
            pulse_width=1,
            rising_edge_step=mt.ceil(abs(width / MOTOR_RESOLUTION)),
            number_of_pulses=num,
            direction=direction_of_sweep,
        )

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.CONSTANT_GATE,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(motor, motor_info)
        yield from bps.prepare(panda, panda_hdf_info)
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)
        yield from bps.kickoff(panda)
        yield from bps.kickoff(panda_pcomp, wait=True)
        yield from bps.kickoff(motor, wait=True)
        yield from bps.complete_all(motor, panda_pcomp, panda, wait=True)

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        for n in range(number_of_sweeps):
            even: bool = n % 2 == 0
            start2, stop2 = (stop, start) if even else (start, stop)
            print(f"Starting sweep {n} with start: {start2}, stop: {stop2}")
            yield from inner_squared_plan(start2, stop2)
            print(f"Completed sweep {n}")
            # yield from inner_squared_plan(start2, stop2)

    yield from inner_plan()
