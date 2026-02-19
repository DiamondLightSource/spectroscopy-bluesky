from bluesky import preprocessors as bpp
from bluesky.utils import MsgGenerator, make_decorator

DATA_DIRECTORY="data_session_directory"
DATA_DIRECTORY_PATH="/dls/p51/data/2026/cm44254-1/tmp"

def set_data_directory_path(data_directory):
    global DATA_DIRECTORY_PATH
    DATA_DIRECTORY_PATH = data_directory

def attach_data_directory_metadata_wrapper(
    plan: MsgGenerator, data_directory =  None
) -> MsgGenerator:

    global DATA_DIRECTORY_PATH
    if data_directory is None:
        data_directory = DATA_DIRECTORY_PATH

    yield from bpp.inject_md_wrapper(plan, md={DATA_DIRECTORY:data_directory})

attach_data_directory_metadata_decorator = make_decorator(
    attach_data_directory_metadata_wrapper
)
