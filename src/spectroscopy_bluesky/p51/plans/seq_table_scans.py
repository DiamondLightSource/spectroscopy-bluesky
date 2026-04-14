import math as mt  # noqa: I001

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from numpy.typing import NDArray
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
    SeqTable,
    SeqTableInfo,
    StaticSeqTableTriggerLogic,
)
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Fly, Line
from collections.abc import Callable

from spectroscopy_bluesky.common.quantity_conversion import (
    si_111_lattice_spacing,
    energy_to_bragg_angle,
)

from spectroscopy_bluesky.p51.plans.sequence_table import (
    SeqTableBuilder,
    SpectrumBasedTrigger,
)

from .common import (
    get_encoder_counts,
    setup_trajectory_scan_pvs,
)


def prepare_seq_table(
    panda: HDFPanda,
    seq_table: SeqTable,
    seq_table_number: int = 1,
    num_repeats: int = 1,
    prescale_as_us: float = 1,
    prepare_panda: bool = True,
) -> Callable[[], MsgGenerator]:
    """Return a function that can be used to prepare and arm (kickoff) a
    panda sequence table

    Args:
        panda (HDFPanda): Panda object to be operated on
        seq_table (SeqTable): Sequence table settings to be applied
        seq_table_number (int): Number of sequence table settings should be applied to.
                                Defaults to 1.
        num_repeats (int, optional): Number of repeats of sequence table. Defaults to 1.
        prescale_as_us (float, optional): _description_. Defaults to 1.
        prepare_panda (bool, optional): If true, add calls to also arm the panda as well
        as the sequence table. Defaults to True.

    Returns:
        Callable[[], MsgGenerator]: _description_

    Yields:
        Iterator[Callable[[], MsgGenerator]]: _description_
    """

    seq_table_info = SeqTableInfo(
        sequence_table=seq_table, repeats=num_repeats, prescale_as_us=prescale_as_us
    )

    seqtable_flyer = StandardFlyer(
        StaticSeqTableTriggerLogic(panda.seq[seq_table_number])
    )

    trigger_info = TriggerInfo(
        number_of_events=len(seq_table),
        trigger=DetectorTrigger.EXTERNAL_LEVEL,
        livetime=1e-5,
        deadtime=1e-5,
    )

    def inner_plan():
        if prepare_panda:
            yield from bps.prepare(panda, trigger_info)
        yield from bps.prepare(seqtable_flyer, seq_table_info, wait=True)

        yield from bps.kickoff(seqtable_flyer)
        # panda is kicked off later - in seq_table_scan

    return inner_plan


def seq_table_non_linear(
    ei: float,
    ef: float,
    de: float,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
) -> MsgGenerator:
    # Start the plan by loading the saved design for this scan

    energies = np.arange(ei, ef + de, de)  # include Ef as last point in the array
    print(f"param\nEi = {ei}, Ef = {ef}, dE = {de}\n")

    angle = energy_to_bragg_angle(si_111_lattice_spacing, energies)

    yield from seq_table_position_scan(
        angle[0],
        angle[-1],
        time_per_sweep,
        angle,
        motor,
        panda,
        number_of_sweeps=1,
    )


def seq_table_uniform_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor,
    panda: HDFPanda,
    num_trajectory_points: int = 10,
    spectrum_triggers: list[SpectrumBasedTrigger] | None = None,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
) -> MsgGenerator:

    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)

    # setup a second seq table for 'spectrum based' triggering :
    panda_dict = {}
    if spectrum_triggers is not None:
        seq_table = (
            SeqTableBuilder()
            .add_spectrum_based_triggers(spectrum_triggers)
            .get_seq_table()
        )

        prepare_triggers_seqtable = prepare_seq_table(
            panda, seq_table, 2, prepare_panda=False
        )
        panda_dict[panda] = [prepare_triggers_seqtable]

    yield from seq_table_position_scan(
        start,
        stop,
        time_per_sweep,
        capture_positions,
        motor=motor,
        panda=panda,
        num_trajectory_points=num_trajectory_points,
        add_sweep_triggers=add_sweep_triggers,
        number_of_sweeps=number_of_sweeps,
        panda_dict=panda_dict,
    )


def seq_table_position_scan(
    start: float,
    stop: float,
    time_per_sweep: float,
    capture_positions: NDArray,
    motor: Motor,
    panda: HDFPanda,
    num_trajectory_points: int = 10,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
    panda_dict: dict[HDFPanda, list[Callable[[], MsgGenerator]]] | None = None,
) -> MsgGenerator:

    time_per_traj_point = time_per_sweep / num_trajectory_points

    print(
        f"Num trajectorypoints : {num_trajectory_points}, "
        f"time per traj point : {time_per_traj_point}"
    )

    # Prepare motor info using trajectory scanning
    spec = Fly(
        time_per_traj_point
        @ (number_of_sweeps * ~Line(motor, start, stop, num_trajectory_points))
    )

    # add points to capture positions on the reverse sweep
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

    # Sequence table has position triggers for one back-and-forth sweep.
    # Use multiple repetitions of seq table to capture subsequent sweeps.
    seqTable_builder = SeqTableBuilder()
    seqTable_builder.convert_to_encoder = get_encoder_counts
    seqTable_builder.add_positions(positions, time1=1, outa1=True, time2=1, outa2=False)
    if add_sweep_triggers:
        seqTable_builder.add_start_end_triggers("outb1", "outc1")

    # initialise if nothing has been passed in
    if panda_dict is None:
        panda_dict = {}

    prepare_position_seqtable = prepare_seq_table(
        panda, seqTable_builder.get_seq_table(), 1, num_seqtable_repeats
    )
    # append position sequence table setup to panda entry (make empty list first
    # if not already present).
    panda_dict.setdefault(panda, []).append(prepare_position_seqtable)

    yield from seq_table_scan(spec, panda_dict, motor=motor)


def seq_table_scan(
    scan_spec: Fly,
    panda_dict: dict[
        HDFPanda, list[Callable[[], MsgGenerator]]
    ],  # dict containing functions to prepare each panda
    motor: Motor,
) -> MsgGenerator:
    pmac = turbo_slit_pmac(motor)

    yield from ensure_connected(pmac, motor)
    yield from setup_trajectory_scan_pvs()

    detectors = panda_dict.keys()
    for detector in detectors:
        yield from ensure_connected(detector)

    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)

    @bpp.stage_decorator([*detectors])
    @bpp.run_decorator()
    def inner_plan():
        # prepare and kickoff panda seq tables
        for _, preparer_funcs in panda_dict.items():
            for prepare in preparer_funcs:
                yield from prepare()

        yield from bps.declare_stream(*detectors, name="primary", collect=True)

        for panda in detectors:
            yield from bps.kickoff(panda)

        # Prepare pmac with the trajectory
        yield from bps.prepare(pmac_trajectory_flyer, scan_spec, wait=True)
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        yield from bps.collect_while_completing(
            flyers=[pmac_trajectory_flyer],
            dets=[*detectors],
            stream_name="primary",
            flush_period=0.5,
        )

    yield from inner_plan()
