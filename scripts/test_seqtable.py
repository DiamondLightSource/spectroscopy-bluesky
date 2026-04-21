from pathlib import PurePath

from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator
from dodal.beamlines.p51 import (
    panda1,
    panda2,
    turbo_slit_pmac,
    turbo_slit_x,
)
from ophyd_async.core import PathProvider, StaticFilenameProvider, StaticPathProvider
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans import (
    seq_table_energy_scan,
    seq_table_two_panda_scan,
    seq_table_uniform_scan,
)
from spectroscopy_bluesky.p51.plans.sequence_table import (
    SpectrumBasedTrigger,
    SpectrumTriggerType,
)


def generate_test_triggers() -> list[SpectrumBasedTrigger]:
    return [
        SpectrumBasedTrigger(
            1,
            output_length=0.25,
            trigger_type=SpectrumTriggerType.START,
            output_ports=[2],
        ),
        SpectrumBasedTrigger(
            1,
            output_length=0.25,
            trigger_type=SpectrumTriggerType.END,
            output_ports=[3],
        ),
        SpectrumBasedTrigger(
            1,
            output_length=0.25,
            trigger_type=SpectrumTriggerType.END,
            output_ports=[5],
        ),
    ]


def static_panda_path_provider() -> PathProvider:
    return StaticPathProvider(
        StaticFilenameProvider("panda.h5"),
        PurePath("/dls/p51/data/2026/cm44254-2/tmp/"),
    )


RE = RunEngine()
path_provider = static_panda_path_provider()

p = panda1(path_provider)
p2 = panda2(path_provider)
ts = turbo_slit_x()
pmac = turbo_slit_pmac(ts)

RE(ensure_connected(p, ts, pmac))


def two_seq_tables_plan() -> MsgGenerator:
    # setup and enable the 2nd sequence table, ready to receive triggers
    # from the 1st sequence table.
    # yield from setup_seq_table_spectrum_triggers(panda_triggers, p, 2)

    yield from seq_table_uniform_scan(
        0,
        5,
        1.0,
        5.0,
        num_trajectory_points=10,
        number_of_sweeps=6,
        add_sweep_triggers=True,
        spectrum_triggers=generate_test_triggers(),
        motor=ts,
        panda=p,
    )


def seq_table_two_panda_plan() -> MsgGenerator:
    # setup and enable the 2nd sequence table, ready to receive triggers
    # from the 1st sequence table.
    # yield from setup_seq_table_spectrum_triggers(panda_triggers, p, 2)

    yield from seq_table_two_panda_scan(
        start=1,
        stop=10,
        stepsize=1,
        time_per_sweep=2,
        add_sweep_triggers=True,
        number_of_sweeps=10,
        spectrum_triggers=generate_test_triggers(),
        motor=ts,
        panda=p,
        panda2=p2,
    )


def energy_scan() -> MsgGenerator:

    yield from seq_table_energy_scan(
        element="Ar",
        edge="K",
        time_per_sweep=8,
        motor=ts,
        panda=p,
    )


RE(two_seq_tables_plan())
RE(seq_table_two_panda_plan())
RE(energy_scan())
