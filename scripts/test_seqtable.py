from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator
from dodal.beamlines.p51 import panda, turbo_slit_pmac, turbo_slit_x
from ophyd_async.fastcs.panda import HDFPanda, SeqTableInfo
from ophyd_async.plan_stubs import ensure_connected

from spectroscopy_bluesky.p51.plans import (
    seq_table,
    setup_seq_table,
)
from spectroscopy_bluesky.p51.plans.sequence_table import (
    SeqTableBuilder,
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


RE = RunEngine()
p = panda()
ts = turbo_slit_x()
pmac = turbo_slit_pmac()

RE(ensure_connected(p, ts, pmac))

panda_triggers = generate_test_triggers()


def setup_seq_table_spectrum_triggers(
    triggers: list[SpectrumBasedTrigger], panda: HDFPanda, seq_table_number: int
) -> MsgGenerator:
    """Setup sequence table using list of SpectrumBasedTriggers

    Args:
        triggers (list[SpectrumBasedTrigger]):
        panda (HDFPanda):
        seq_table_number (int): sequence table number on Panda to be setup
        (usually either 1 or 2)

    Returns:
        MsgGenerator:

    Yields:
        Iterator[MsgGenerator]:
    """
    seq_table = SeqTableBuilder().add_spectrum_based_triggers(triggers).get_seq_table()
    seq_table_info = SeqTableInfo(sequence_table=seq_table, repeats=1, prescale_as_us=1)
    yield from setup_seq_table(seq_table_info, panda, seq_table_number)


def two_seq_tables_plan() -> MsgGenerator:
    # setup and enable the 2nd sequence table, ready to receive triggers
    # from the 1st sequence table.
    yield from setup_seq_table_spectrum_triggers(panda_triggers, p, 2)

    yield from seq_table(
        0,
        10,
        1.0,
        1.0,
        num_trajectory_points=10,
        number_of_sweeps=6,
        add_sweep_triggers=True,
        motor=ts,
        panda=p,
    )


RE(two_seq_tables_plan())
