import logging
from logging import Logger
from pathlib import PurePath

import bluesky.plan_stubs as bps
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.plans import scan
from bluesky.utils import MsgGenerator
from dodal.beamlines.i18 import panda3
from dodal.common.beamlines.beamline_utils import (
    set_path_provider,
)
from ophyd_async.core import (
    PathProvider,
    StaticFilenameProvider,
    StaticPathProvider,
    init_devices,
)
from ophyd_async.sim import SimMotor

from spectroscopy_bluesky.common.devices.panda_detector import PandaDetector
from spectroscopy_bluesky.common.panda_data_socket import DataSocket

i18_data_path = "/dls/i18/data/2025/cm40636-5/tmp/"
i20_1_data_path = "dls/i20-1/data/2023/cm33897-5/bluesky"


def static_panda_path_provider(dir_path) -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("panda.h5"),
        PurePath(dir_path),
    )


set_path_provider(static_panda_path_provider(i18_data_path))

bec = BestEffortCallback()
RE = RunEngine({})
RE.subscribe(bec)
with init_devices():
    panda_device = panda3()
    sim_motor = SimMotor("sim_motor")

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)


def setup_logging(level, *objs_list):
    for obj in objs_list:
        if hasattr(obj, "logger"):
            logger: Logger = getattr(obj, "logger")
            logger.setLevel(level)
            if stream_handler not in logger.handlers:
                logger.addHandler(stream_handler)


# panda_socket = DataSocket("bl51p-ts-panda-02", 8889)
panda_socket = DataSocket("bl18i-mo-panda-03", 8889)
panda_socket.connect()
socket_data_dict = {"counts1": "COUNTER1.OUT", "counts2": "COUNTER2.OUT"}

panda_detector = PandaDetector(
    "panda_detector", panda_device, panda_socket, socket_data_dict
)
panda_detector.frame_time = 1000
panda_detector.dead_time = 0
panda_detector.sleep_time = 0
panda_detector.use_hdf_writer = True

setup_logging(logging.INFO, panda_socket, panda_detector)


def prepare_panda() -> MsgGenerator:
    yield from bps.prepare(panda_detector, 1, wait=True)
    yield from bps.trigger(panda_detector, wait=True)


# RE(prepare_panda())

RE(scan([panda_detector], sim_motor, 0, 10, 11))
