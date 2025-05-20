import asyncio
import math as mt

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
from aioca import caput
from bluesky.utils import MsgGenerator

# from dodal.beamlines.i20_1 import panda, turbo_slit
from dodal.beamlines.i20_1 import turbo_slit
from dodal.common.coordination import inject
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator
from ophyd_async.core import (
    DetectorTrigger,
    StandardFlyer,
    TriggerInfo,
    wait_for_value,
)
from ophyd_async.epics.motor import FlyMotorInfo
from ophyd_async.epics.pmac import (
    Pmac,
    PmacMotor,
    PmacTrajectoryTriggerLogic,
    PmacTrajInfo,
)
from ophyd_async.fastcs.panda import (
    HDFPanda,
    PandaPcompDirection,
    PcompInfo,
    StaticPcompTriggerLogic,
)
from ophyd_async.fastcs.panda._block import PcompBlock
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Line, Repeat, fly

MOTOR_RESOLUTION = -1 / 10000
# pmac = Pmac(prefix="BL20J-MO-STEP-06",name="pmac")


class _StaticPcompTriggerLogic(StaticPcompTriggerLogic):
    """For controlling the PandA `PcompBlock` when flyscanning."""

    def __init__(self, pcomp: PcompBlock) -> None:
        self.pcomp = pcomp

    async def kickoff(self) -> None:
        await wait_for_value(self.pcomp.active, True, timeout=1)

    async def prepare(self, value: PcompInfo) -> None:
        await caput("BL20J-EA-PANDA-02:SRGATE1:FORCE_RST", "1", wait=True)
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
        if width / MOTOR_RESOLUTION > 0
        else PandaPcompDirection.NEGATIVE
    )

    return width, start, stop, direction_of_sweep


def get_pcomp_info(width, start_pos, direction_of_sweep: PandaPcompDirection, num):
    start_pos_pcomp = mt.floor(start_pos / MOTOR_RESOLUTION)
    rising_edge_step = mt.ceil(abs(width / MOTOR_RESOLUTION))

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
    start: float,
    stop: float,
    num: int,
    duration: float,
    panda: HDFPanda = inject("panda"),  # noqa: B008
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

        motor = turbo_slit().xfine
        # move motor to initial position
        yield from bps.prepare(motor, motor_info, wait=True)

        # prepare pcomp
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)
        yield from bps.kickoff(panda_pcomp, wait=True)

        # kickoff motor move once pcomp has started
        yield from bps.kickoff(motor, wait=True)

        yield from bps.complete_all(motor, panda_pcomp, wait=True)

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
        yield from bps.kickoff(panda, wait=True)

        for n in range(number_of_sweeps):
            even: bool = n % 2 == 0
            start2, stop2 = (start, stop) if even else (stop, start)
            print(f"Starting sweep {n} with start: {start2}, stop: {stop2}")
            yield from inner_squared_plan(start2, stop2)
            print(f"Completed sweep {n}")

        yield from bps.complete_all(panda, wait=True)

    panda_hdf_info = TriggerInfo(
        number_of_events=num * number_of_sweeps,
        trigger=DetectorTrigger.CONSTANT_GATE,
        livetime=duration,
        deadtime=1e-5,
    )

    yield from inner_plan()


def fly_sweep_both_ways(
    start: float,
    stop: float,
    num: int,
    duration: float,
    panda: HDFPanda = inject("panda"),  # noqa: B008
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

        motor = turbo_slit().xfine

        # move motor to initial position
        yield from bps.prepare(motor, motor_info, wait=True)

        # kickoff motor move once pcomp has started
        yield from bps.kickoff(motor, wait=True)

        yield from bps.complete_all(motor, panda_pcomp, wait=True)

    @attach_data_session_metadata_decorator()
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

        motor = turbo_slit().xfine
        yield from bps.prepare(motor, motor_info, wait=True)

        # prepare both pcomps
        yield from bps.prepare(panda_pcomp1, pcomp_info1, wait=True)
        yield from bps.prepare(panda_pcomp2, pcomp_info2, wait=True)

        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
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

        yield from bps.complete_all(panda, wait=True)

    panda_hdf_info = TriggerInfo(
        number_of_events=num * number_of_sweeps,
        trigger=DetectorTrigger.CONSTANT_GATE,
        livetime=duration,
        deadtime=1e-5,
    )

    yield from inner_plan()


def trajectory_fly_scan(
    start: float,
    stop: float,
    num: int,
    duration: float,
    panda: HDFPanda = inject("panda"),  # noqa: B008
    number_of_sweeps: int = 5,
) -> MsgGenerator:
    panda_pcomp1 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[1]))
    panda_pcomp2 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[2]))

    pmac = Pmac(prefix="BL20J-MO-STEP-06", name="pmac")
    motor = PmacMotor(prefix="BL20J-OP-PCHRO-01:TS:XFINE", name="X")

    yield from ensure_connected(pmac, motor)

    spec = fly(
        Repeat(number_of_sweeps, gap=True) * ~Line(motor, start, stop, num),
        duration,
    )

    info = PmacTrajInfo(spec=spec)

    traj = PmacTrajectoryTriggerLogic(pmac)
    traj_flyer = StandardFlyer(traj)

    @attach_data_session_metadata_decorator()
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
            trigger=DetectorTrigger.CONSTANT_GATE,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(traj_flyer, info, wait=True)
        # prepare both pcomps
        yield from bps.prepare(panda_pcomp1, pcomp_info1, wait=True)
        yield from bps.prepare(panda_pcomp2, pcomp_info2, wait=True)
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)

        yield from bps.kickoff(panda, wait=True)
        yield from bps.kickoff(traj_flyer, wait=True)

        yield from bps.complete_all(traj_flyer, panda, wait=True)

    yield from inner_plan()
