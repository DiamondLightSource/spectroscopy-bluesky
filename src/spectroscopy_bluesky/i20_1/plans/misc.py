from bluesky.plan_stubs import sleep
from bluesky.utils import MsgGenerator
from dodal.beamlines.i20_1 import create_static_path_provider
from dodal.common.beamlines.beamline_utils import (
    set_path_provider,
)


def set_static_path_provider(file_path: str) -> MsgGenerator:
    """Set the data output directory to be used by Nexus data writer and Panda Hdf writer.

    Args:
        file_path (str): Full path to data directory
    """

    set_path_provider(create_static_path_provider(file_path))
    yield from sleep(0)
