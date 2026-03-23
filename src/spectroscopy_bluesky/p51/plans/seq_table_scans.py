import math as mt

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.utils import MsgGenerator
from dodal.beamlines.p51 import turbo_slit_pmac
from dodal.common.coordination import inject
from ophyd_async.core import (
    DetectorTrigger,
    StandardFlyer,
    TriggerInfo,
)
from ophyd_async.epics.motor import Motor
from ophyd_async.epics.pmac import (
    PmacTrajectoryTriggerLogic,
)
from ophyd_async.fastcs.panda import (
    HDFPanda,
    SeqTableInfo,
    StaticSeqTableTriggerLogic,
)
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Fly, Line

from spectroscopy_bluesky.common.quantity_conversion import (
    energy_to_bragg_angle,
    si_111_lattice_spacing,
)
from spectroscopy_bluesky.p51.plans.sequence_table import (
    SeqTableBuilder,
    SpectrumBasedTrigger,
    SpectrumTriggerType,
)

from .common import (
    get_encoder_counts,
    setup_trajectory_scan_pvs,
)


def generate_test_triggers() -> list[SpectrumBasedTrigger]:
    return [
        SpectrumBasedTrigger(
            1,
            output_length=0.00002,
            trigger_type=SpectrumTriggerType.START,
            output_ports=[2],
        ),
        SpectrumBasedTrigger(
            1,
            output_length=0.00002,
            trigger_type=SpectrumTriggerType.END,
            output_ports=[3],
        ),
        SpectrumBasedTrigger(
            1,
            output_length=0.00002,
            trigger_type=SpectrumTriggerType.END,
            output_ports=[5],
        ),
    ]


def seq_table(
    start: float,
    stop: float,
    stepsize: float,
    time_per_point: float,
    motor: Motor,  # noqa: B008
    detectors: list[HDFPanda],  # noqa: B008
    num_trajectory_points: int = 10,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
) -> MsgGenerator:
    num_seq_points = int((stop - start) / stepsize) + 1

    time_per_traj_point = (num_seq_points / num_trajectory_points) * time_per_point
    print(
        f"Num seq points : {num_seq_points}, "
        f"time per traj point : {time_per_traj_point}"
    )

    # Prepare motor info using trajectory scanning
    spec = Fly(
        time_per_traj_point
        @ (number_of_sweeps * ~Line(motor, start, stop, num_trajectory_points))
    )

    # add points to capture positions on the reverse sweep
    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)

    if number_of_sweeps > 1:
        num_captures = capture_positions.size
        positions = np.zeros(2 * num_captures)
        positions[0:num_captures] = capture_positions
        positions[num_captures : num_captures * 2] = np.flip(capture_positions)
    else:
        positions = capture_positions

    num_seqtable_repeats = 1
    if number_of_sweeps > 1:
        num_seqtable_repeats = mt.ceil(number_of_sweeps / 2)

    seq_table_info = []
    for dets in detectors:
        if "panda1" in dets.name:
            # Sequence table has position triggers for one back-and-forth sweep.
            # Use multiple repetitions of sequence table to capture subsequent sweeps.
            seqTabl1_builder = SeqTableBuilder()
            seqTabl1_builder.convert_to_encoder = get_encoder_counts
            seqTabl1_builder.add_positions(
                positions, time1=1, outa1=True, time2=1, outa2=False
            )
            if add_sweep_triggers:
                seqTabl1_builder.add_start_end_triggers("outb1", "outc1")
            seqTable1_info = SeqTableInfo(
                sequence_table=seqTabl1_builder.get_seq_table(),
                repeats=num_seqtable_repeats,
                prescale_as_us=1,
            )
            seq_table_info += [seqTable1_info]

        if "panda2" in dets.name:
            triggers = generate_test_triggers()
            seqTabl2_builder = SeqTableBuilder().add_spectrum_based_triggers(triggers)
            seqTable2_info = SeqTableInfo(
                sequence_table=seqTabl2_builder.get_seq_table(),
                repeats=num_seqtable_repeats,
                prescale_as_us=1,
            )
            seq_table_info += [seqTable2_info]

    yield from seq_table_scan(
        scan_spec=spec, seq_table_info=seq_table_info, motor=motor, detectors=detectors
    )


# run_plan("seq_non_linear", ei=6000.0, ef=10000.0, de=100.0, duration=0.1)
def seq_non_linear(
    ei: float,
    ef: float,
    de: float,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
) -> MsgGenerator:
    # Start the plan by loading the saved design for this scan

    energies = np.arange(ei, ef + de, de)  # include Ef as last point in the array
    print(f"param\nEi = {ei}, Ef = {ef}, dE = {de}\n")

    angle = energy_to_bragg_angle(si_111_lattice_spacing, energies)

    # Prepare motor info using trajectory scanning
    spec = Fly(duration @ (Line(motor, angle[0], angle[-1], len(angle))))

    builder = SeqTableBuilder()
    builder.convert_to_encoder = get_encoder_counts
    builder.add_positions(
        angle,
        time1=1,
        time2=1,
        outa1=True,
        outb1=True,
        outa2=False,
        outb2=True,
    )

    seq_table_info = SeqTableInfo(
        sequence_table=builder.get_seq_table(), repeats=1, prescale_as_us=1
    )

    yield from seq_table_scan(spec, [seq_table_info], motor=motor, detectors=[panda])


def setup_seq_table(
    seq_table_info: SeqTableInfo, panda: HDFPanda, seq_table_number: int = 1
):
    panda_seq = StandardFlyer(StaticSeqTableTriggerLogic(panda.seq[seq_table_number]))
    yield from bps.prepare(panda_seq, seq_table_info, wait=True)
    yield from bps.kickoff(panda_seq, wait=True)


def create_trigger_info(sti: SeqTableInfo) -> TriggerInfo:
    return TriggerInfo(
        number_of_events=len(
            sti.sequence_table
        ),  # same as number of rows in sequence table
        trigger=DetectorTrigger.EXTERNAL_LEVEL,
        livetime=1e-5,
        deadtime=1e-5,
    )


def seq_table_scan(
    scan_spec: Fly,
    seq_table_info: list[SeqTableInfo],
    motor: Motor,  # noqa: B008
    detectors: list[HDFPanda],  # noqa: B008
) -> MsgGenerator:
    pmac = turbo_slit_pmac(motor)

    yield from ensure_connected(pmac, motor)
    for detector in detectors:
        yield from ensure_connected(detector)
    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)

    trigger_info = [create_trigger_info(sti) for sti in seq_table_info]

    sequence_table = [
        StandardFlyer(StaticSeqTableTriggerLogic(det.seq[1])) for det in detectors
    ]

    yield from setup_trajectory_scan_pvs()

    @bpp.stage_decorator([*detectors])
    @bpp.run_decorator()
    def inner_plan():

        # Prepare pmac with the trajectory
        yield from bps.prepare(pmac_trajectory_flyer, scan_spec, wait=True)

        # prepare panda and sequencer table
        for index, detector in enumerate(detectors):
            yield from bps.prepare(detector, trigger_info[index], wait=True)
            yield from bps.prepare(
                sequence_table[index], seq_table_info[index], wait=True
            )

        yield from bps.declare_stream(*detectors, name="primary", collect=True)

        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        # kickoff panda and sequence tables waiting for all of them
        for index, detector in enumerate(detectors):
            yield from bps.kickoff(sequence_table[index], wait=True)
            yield from bps.kickoff(detector, wait=True)

        yield from bps.collect_while_completing(
            flyers=[pmac_trajectory_flyer],
            dets=[*detectors],
            stream_name="primary",
            flush_period=0.5,
        )

    yield from inner_plan()
