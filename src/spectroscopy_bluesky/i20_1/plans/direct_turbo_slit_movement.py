import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.plans import count
from bluesky.protocols import Movable, Readable
from bluesky.utils import MsgGenerator
from dodal.beamlines.i20_1 import turbo_slit
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator
from ophyd_async.epics.motor import FlyMotorInfo
from dodal.common.visit import LocalDirectoryServiceClient, StaticVisitPathProvider
from ophyd_async.fastcs.panda import HDFPanda, StaticPcompTriggerLogic, PcompInfo, PandaPcompDirection
from pathlib import Path
from ophyd_async.core import StandardFlyer, TriggerInfo, DetectorTrigger, StaticPathProvider, UUIDFilenameProvider
import math as mt

path_provider = StaticPathProvider(
    UUIDFilenameProvider(),
    Path("/dls/i20-1/data/2023/cm33897-5/bluesky"),
)

panda = HDFPanda(
    f"BL20J-EA-PANDA-02:",
    path_provider=path_provider,
    name="panda"
)


def continuous_movement(
    motors: list[Movable] | None = None, devices: list[Readable] | None = None
) -> MsgGenerator:
    if motors is None:
        motors = []
    if devices is None:
        devices = []
    # yield from bps.stage_all(*devices)
    # yield from bps.open_run()
    yield from count(*devices, *motors)
    print("empty run")
    # yield from bps.close_run()
    # yield from bps.unstage_all(*devices)


@attach_data_session_metadata_decorator()
def step_scan_one_motor(
    start: int,
    stop: int,
    step: int,
    motor: Movable,
    devices: list[Readable] | None = None,
) -> MsgGenerator:
    print(f"motor: {motor}, devices: {devices}")
    if devices is None:
        devices = []
    yield from bps.stage_all(*devices, motor)
    yield from bps.open_run()
    yield from bps.abs_set(motor.velocity, 1)
    print("preparing the run")
    yield from bps.mv(motor, start)
    for s in np.linspace(start, stop, step):
        yield from bps.mv(motor, s)
        for r in devices:
            yield from bps.trigger_and_read([r])
    print("run finished")
    yield from bps.close_run()
    yield from bps.unstage_all(*devices, motor)


def fly_scan_ts(
    start: int,
    stop: int,
    num: int,
    duration: float,
) -> MsgGenerator:

    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda,panda_pcomp])
    def inner_plan():
        motor = turbo_slit().xfine
        width = (((stop - start) / (num - 1)))
        start_pos = start - (width / 2)
        stop_pos = stop + (width / 2)
        MRES = -1/10000
        motor_info = FlyMotorInfo(
            start_position=start_pos, end_position=stop_pos, time_for_move=num * duration
        )
        panda_pcomp_info = PcompInfo(
            start_postion = mt.ceil(start_pos / (MRES)),
            pulse_width = 1,
            rising_edge_step = mt.ceil(abs(width/MRES)),
            number_of_pulses = num,
            direction = PandaPcompDirection.POSITIVE if width/MRES > 0 else PandaPcompDirection.NEGATIVE
        )

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.CONSTANT_GATE,
            livetime=duration,
            deadtime=1e-5,

        )

        yield from bps.prepare(motor, motor_info)
        yield from bps.prepare(panda, panda_hdf_info)
        yield from bps.prepare(panda_pcomp, panda_pcomp_info,wait=True)
        yield from bps.kickoff(panda)
        yield from bps.kickoff(panda_pcomp,wait=True)
        yield from bps.kickoff(motor, wait=True)
        yield from bps.complete_all(motor,panda_pcomp,panda,wait=True)
    yield from inner_plan()
