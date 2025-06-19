from pathlib import Path

import bluesky.plan_stubs as bps
import numpy as np
from bluesky.plans import count
from bluesky.protocols import Movable, Readable
from bluesky.utils import MsgGenerator

# from dodal.beamlines.i20_1 import panda, turbo_slit
# from dodal.beamlines.i20_1 import turbo_slit
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator

path_provider = StaticPathProvider(
    UUIDFilenameProvider(),
    Path("/dls/i20-1/data/2023/cm33897-5/bluesky"),
)

panda = HDFpanda("BL20J-EA-panda-02:", path_provider=path_provider, name="panda")


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
