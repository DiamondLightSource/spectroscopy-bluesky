import asyncio
import math as mt

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from aioca import caput
from bluesky.utils import MsgGenerator
from dodal.beamlines.p51 import turbo_slit_pmac
from dodal.common.coordination import inject
from ophyd_async.core import (
    DetectorTrigger,
    FlyMotorInfo,
    StandardFlyer,
    TriggerInfo,
    wait_for_value,
)
from ophyd_async.epics.motor import Motor
from ophyd_async.epics.pmac import (
    PmacTrajectoryTriggerLogic,
)
from ophyd_async.fastcs.panda import (
    HDFPanda,
    PandaPcompDirection,
    PcompInfo,
    StaticPcompTriggerLogic,
)
from ophyd_async.fastcs.panda._block import PcompBlock
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Fly, Line

from .common import (
    get_encoder_counts,
    setup_trajectory_scan_pvs,
)


class _StaticPcompTriggerLogic(StaticPcompTriggerLogic):
    """For controlling the PandA `PcompBlock` when flyscanning."""

    def __init__(self, pcomp: PcompBlock) -> None:
        self.pcomp = pcomp

    async def kickoff(self) -> None:
        await wait_for_value(self.pcomp.active, True, timeout=1)

    async def prepare(self, value: PcompInfo) -> None:
        await caput("BL51P-EA-PANDA-02:SRGATE1:FORCE_RST", "1", wait=True)
        await asyncio.gather(
            self.pcomp.start.set(value.start_postion),
            self.pcomp.width.set(value.pulse_width),
            self.pcomp.step.set(value.rising_edge_step),
            self.pcomp.pulses.set(value.number_of_pulses),
            self.pcomp.dir.set(value.direction),
        )

    async def stop(self):
        pass


def calculate_stuff(start, stop, num):
    width = (stop - start) / (num - 1)
    direction_of_sweep = (
        PandaPcompDirection.POSITIVE
        if get_encoder_counts(width, 0) > 0
        else PandaPcompDirection.NEGATIVE
    )

    return width, start, stop, direction_of_sweep


def get_pcomp_info(width, start_pos, direction_of_sweep: PandaPcompDirection, num):
    start_pos_pcomp = mt.floor(get_encoder_counts(start_pos))
    rising_edge_step = mt.ceil(abs(get_encoder_counts(width, 0)))

    panda_pcomp_info = PcompInfo(
        start_postion=start_pos_pcomp,
        pulse_width=1,
        rising_edge_step=rising_edge_step,
        number_of_pulses=num,
        direction=direction_of_sweep,
    )

    return panda_pcomp_info


def fly_scan_ts(
    start: int,
    stop: int,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
) -> MsgGenerator:
    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        width = (stop - start) / (num - 1)
        start_pos = start - (width / 2)
        stop_pos = stop + (width / 2)
        motor_info = FlyMotorInfo(
            start_position=start_pos,
            end_position=stop_pos,
            time_for_move=num * duration,
        )
        panda_pcomp_info = PcompInfo(
            start_postion=mt.ceil(get_encoder_counts(start_pos)),
            pulse_width=1,
            rising_edge_step=mt.ceil(abs(get_encoder_counts(width, 0))),
            number_of_pulses=num,
            direction=PandaPcompDirection.POSITIVE
            if get_encoder_counts(width) > 0
            else PandaPcompDirection.NEGATIVE,
        )

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.EXTERNAL_LEVEL,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(motor, motor_info, wait=True)
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)
        yield from bps.declare_stream(panda, name="primary", collect=True)
        yield from bps.kickoff(panda, wait=True)
        yield from bps.kickoff(panda_pcomp, wait=True)
        yield from bps.kickoff(motor, wait=True)
        yield from bps.collect_while_completing(
            flyers=[motor],
            dets=[panda],
            stream_name="primary",
            flush_period=0.5,
        )

    yield from inner_plan()


def fly_sweep(
    start: float,
    stop: float,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    number_of_sweeps: int = 5,
    runup: float = 0.0,
) -> MsgGenerator:
    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    def inner_squared_plan(start: float | int, stop: float | int):
        width, start_pos, stop_pos, direction_of_sweep = calculate_stuff(
            start, stop, num
        )

        direction_multiplier = -1.0
        if start < stop:
            direction_multiplier = 1.0

        motor_info = FlyMotorInfo(
            # include extra runup distance on start and end positions
            start_position=start_pos - direction_multiplier * runup,
            end_position=stop_pos + direction_multiplier * runup,
            time_for_move=num * duration,
        )

        panda_pcomp_info = get_pcomp_info(width, start_pos, direction_of_sweep, num)

        # move motor to initial position
        yield from bps.prepare(motor, motor_info, wait=True)

        # prepare pcomp
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)

        yield from bps.kickoff(panda_pcomp, wait=True)

        # kickoff motor move once pcomp has started
        yield from bps.kickoff(motor, wait=True)

        yield from bps.collect_while_completing(
            flyers=[motor],
            dets=[panda],
            stream_name="primary",
            flush_period=0.5,
        )

    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
        yield from bps.declare_stream(panda, name="primary", collect=True)
        yield from bps.kickoff(panda, wait=True)

        for n in range(number_of_sweeps):
            even: bool = n % 2 == 0
            start2, stop2 = (start, stop) if even else (stop, start)
            print(f"Starting sweep {n} with start: {start2}, stop: {stop2}")
            yield from inner_squared_plan(start2, stop2)
            print(f"Completed sweep {n}")

    panda_hdf_info = TriggerInfo(
        number_of_events=num * number_of_sweeps,
        trigger=DetectorTrigger.EXTERNAL_LEVEL,
        livetime=duration,
        deadtime=1e-5,
    )

    yield from inner_plan()


def fly_sweep_both_ways(
    start: float,
    stop: float,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    number_of_sweeps: int = 5,
) -> MsgGenerator:
    panda_pcomp1 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[1]))
    panda_pcomp2 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[2]))

    def inner_squared_plan(start: float, stop: float, panda_pcomp: StandardFlyer):
        motor_info = FlyMotorInfo(
            # include extra runup distance on start and end positions
            start_position=start,
            end_position=stop,
            time_for_move=num * duration,
        )

        # move motor to initial position
        yield from bps.prepare(motor, motor_info, wait=True)

        # kickoff motor move once pcomp has started
        yield from bps.kickoff(motor, wait=True)

        yield from bps.collect_while_completing(
            flyers=[motor],
            dets=[panda],
            stream_name="primary",
            flush_period=0.5,
        )

    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp1, panda_pcomp2])
    def inner_plan():
        width, _, _, direction_of_sweep = calculate_stuff(start, stop, num)

        dir1 = direction_of_sweep
        dir2 = (
            PandaPcompDirection.POSITIVE
            if direction_of_sweep == PandaPcompDirection.NEGATIVE
            else PandaPcompDirection.NEGATIVE
        )

        pcomp_info1 = get_pcomp_info(width, start, dir1, num)

        pcomp_info2 = get_pcomp_info(width, stop, dir2, num)

        motor_info = FlyMotorInfo(
            # include extra runup distance on start and end positions
            start_position=start,
            end_position=stop,
            time_for_move=num * duration,
        )

        yield from bps.prepare(motor, motor_info, wait=True)

        # prepare both pcomps
        yield from bps.prepare(panda_pcomp1, pcomp_info1, wait=True)
        yield from bps.prepare(panda_pcomp2, pcomp_info2, wait=True)

        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
        yield from bps.declare_stream(panda, name="primary", collect=True)

        yield from bps.kickoff(panda, wait=True)

        for n in range(number_of_sweeps):
            even: bool = n % 2 == 0
            start2, stop2 = (start, stop) if even else (stop, start)
            panda_pcomp = panda_pcomp1
            if not even:
                panda_pcomp = panda_pcomp2
            print(f"Starting sweep {n} with start: {start2}, stop: {stop2}")
            yield from inner_squared_plan(start2, stop2, panda_pcomp)
            print(f"Completed sweep {n}")

    panda_hdf_info = TriggerInfo(
        number_of_events=num * number_of_sweeps,
        trigger=DetectorTrigger.EXTERNAL_LEVEL,
        livetime=duration,
        deadtime=1e-5,
    )

    yield from inner_plan()


def trajectory_fly_scan(
    start: float,
    stop: float,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
) -> MsgGenerator:
    panda_pcomp1 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[1]))
    panda_pcomp2 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[2]))
    pmac = turbo_slit_pmac(motor)

    yield from ensure_connected(pmac, motor)

    yield from setup_trajectory_scan_pvs()

    spec = Fly(float(duration) @ (Line(motor, start, stop, num)))

    trigger_logic = spec
    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)

    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp1, panda_pcomp2])
    def inner_plan():
        width, _, _, direction_of_sweep = calculate_stuff(start, stop, num)

        dir1 = direction_of_sweep
        dir2 = (
            PandaPcompDirection.POSITIVE
            if direction_of_sweep == PandaPcompDirection.NEGATIVE
            else PandaPcompDirection.NEGATIVE
        )

        pcomp_info1 = get_pcomp_info(width, start, dir1, num)
        pcomp_info2 = get_pcomp_info(width, stop, dir2, num)

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.EXTERNAL_LEVEL,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(pmac_trajectory_flyer, trigger_logic, wait=True)
        # prepare both pcomps
        yield from bps.prepare(panda_pcomp1, pcomp_info1, wait=True)
        yield from bps.prepare(panda_pcomp2, pcomp_info2, wait=True)
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)

        yield from bps.declare_stream(panda, name="primary", collect=True)

        yield from bps.kickoff(panda, wait=True)
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        yield from bps.collect_while_completing(
            flyers=[pmac_trajectory_flyer],
            dets=[panda],
            stream_name="primary",
            flush_period=0.5,
        )

    yield from inner_plan()
