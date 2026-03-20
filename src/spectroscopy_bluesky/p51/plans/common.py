import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator
from dodal.common.coordination import inject
from ophyd_async.core import (
    YamlSettingsProvider,
)
from ophyd_async.epics.core import epics_signal_rw
from ophyd_async.fastcs.panda import (
    HDFPanda,
    apply_panda_settings,
)
from ophyd_async.plan_stubs import (
    apply_settings,
    ensure_connected,
    retrieve_settings,
    store_settings,
)

# Motor resolution used to conert between user position and motor encoder counts
MRES = -1 / 10000

# default offset count to be applied when converting user positions to encoder counts.
ENCODER_OFFSET_COUNTS = 0


def get_encoder_counts(user_position: float, offset=ENCODER_OFFSET_COUNTS) -> float:
    """Convert from user position to motor encoder counts
    (using MRES global variable).

    Args:
        user_position : user position
        offset (optional): Count offset to be added after the conversion.
            Defaults to ENCODER_OFFSET_COUNTS (=0).

    Returns:
        motor encoder counts
    """
    return user_position / MRES + offset


def setup_trajectory_scan_pvs(prefix: str = "BL51P-MO-STEP-06"):
    """
    Set PV values on trajectory scan controller needed for scan to work
    (axis label to X, and profile name to PMAC6CS3)
    """
    cs_axis_label = epics_signal_rw(str, prefix + ":M4:CsAxis", name="cs_axis_label")
    cs_profile_name = epics_signal_rw(
        str, prefix + ":ProfileCsName", name="cs_profile_name"
    )
    yield from ensure_connected(cs_axis_label, cs_profile_name)

    # set the CS axis label and profile names
    yield from bps.mv(cs_axis_label, "X", cs_profile_name, "PMAC6CS3")
    yield from bps.sleep(0.5)  # wait for the records to update


def restore_panda_settings(
    panda1: HDFPanda = inject("panda1"),  # noqa: B008
    panda2: HDFPanda = inject("panda2"),  # noqa: B008
    restoreAll: bool = False,
) -> MsgGenerator:
    if restoreAll:
        yield from plan_restore_settings(panda=panda1, name="seq_table")
    yield from plan_restore_dataset_settings(panda=panda1, name="seq_table")
    yield from plan_restore_dataset_settings(panda=panda2, name="seq_table2")


def plan_store_settings(panda: HDFPanda, name: str):
    provider = YamlSettingsProvider(
        "/workspace_git/spectroscopy_bluesky/src/spectroscopy_bluesky/p51/layouts"
    )
    yield from store_settings(provider, name, panda)


def plan_restore_dataset_settings(panda: HDFPanda, name: str):
    """Apply dataset settings to a panda device."""
    provider = YamlSettingsProvider(
        "/workspace_git/spectroscopy_bluesky/src/spectroscopy_bluesky/p51/layouts"
    )
    settings = yield from retrieve_settings(provider, name, panda)
    dataset, others = settings.partition(
        lambda signal: (
            signal.name.endswith("_dataset")
            and any(k in signal.name for k in ["out", "val", "pos"])
        )
    )
    new_dataset = {
        signal: (value if value else signal.name.replace(".", "_"))
        for signal, value in dataset.items()
    }
    yield from apply_settings(new_dataset)


def plan_restore_settings(panda: HDFPanda, name: str):
    print(f"\nrestoring {name} layout\n")
    provider = YamlSettingsProvider(
        "/workspace_git/spectroscopy_bluesky/src/spectroscopy_bluesky/p51/layouts"
    )
    settings = yield from retrieve_settings(provider, name, panda)
    yield from apply_panda_settings(settings)
