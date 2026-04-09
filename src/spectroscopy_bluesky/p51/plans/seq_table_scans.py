import math as mt
from typing import Any

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
from spectroscopy_bluesky.common.xas_scans import (
    XasScanParameters,
    XasScanPointGenerator,
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


class PandaScanConfig:
    def __init__(self):
        self.trigger_info = []
        self.seq_tables = []

    def record_total_trigger_events(self, number_of_events: int):
        trigger_info = TriggerInfo(
            number_of_events=number_of_events,
            trigger=DetectorTrigger.EXTERNAL_LEVEL,
            livetime=1e-5,
            deadtime=1e-5,
        )
        self.trigger_info.append(trigger_info)

    def record_seq_table(self, seq_table: StandardFlyer):
        self.seq_tables.append(seq_table)


def setup_seq_table(
    seq_table_info: SeqTableInfo, panda: HDFPanda, seq_table_number: int = 1
):
    panda_seq = StandardFlyer(StaticSeqTableTriggerLogic(panda.seq[seq_table_number]))
    yield from bps.prepare(panda_seq, seq_table_info, wait=True)
    yield from bps.kickoff(panda_seq, wait=True)


def generate_spectrum_triggers() -> list[SpectrumBasedTrigger]:
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


def generate_position_triggers(
    start: float,
    stop: float,
    stepsize: float,
    number_of_sweeps: int = 4,
) -> list[float]:
    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)

    if number_of_sweeps > 1:
        num_captures = capture_positions.size
        positions = np.zeros(2 * num_captures)
        positions[0:num_captures] = capture_positions
        positions[num_captures : num_captures * 2] = np.flip(capture_positions)
    else:
        positions = capture_positions

    return positions


def prepare_seq_table(
    triggers: list[Any],
    num_seqtable_repeats: int,
    panda: HDFPanda,
    detector_dict: dict[HDFPanda, PandaScanConfig],
    seq_table_number: int = 1,
    is_position_trigger: bool = False,
    is_spectrum_trigger: bool = False,
    add_sweep_triggers: bool = False,
    prescale_as_us: int = 1,
):
    seq_table_builder = SeqTableBuilder()

    if is_position_trigger:
        seq_table_builder.convert_to_encoder = get_encoder_counts
        seq_table_builder.add_positions(triggers, time1=1, time2=1, outa1=1, outa2=0)

    if is_spectrum_trigger:
        seq_table_builder.add_spectrum_based_triggers(triggers)

    if add_sweep_triggers:
        seq_table_builder.add_start_end_triggers("outb1", "outc1")

    seq_table_info = SeqTableInfo(
        sequence_table=seq_table_builder.get_seq_table(),
        repeats=num_seqtable_repeats,
        prescale_as_us=prescale_as_us,
    )

    panda_seq = StandardFlyer(StaticSeqTableTriggerLogic(panda.seq[seq_table_number]))
    yield from bps.prepare(panda_seq, seq_table_info, wait=True)

    detector_dict[panda].record_total_trigger_events(len(seq_table_info.sequence_table))
    detector_dict[panda].record_seq_table(seq_table=panda_seq)


def prepare_pandas_for_scan(
    detector_dict: dict[HDFPanda, PandaScanConfig],
):
    for panda, config in detector_dict.items():
        for trigger_info in config.trigger_info:
            yield from bps.prepare(panda, trigger_info, wait=True)


def kickoff_seqtables_and_pandas(
    detector_dict: dict[HDFPanda, PandaScanConfig],
):
    for panda, config in detector_dict.items():
        for seq_table in config.seq_tables:
            yield from bps.kickoff(seq_table, wait=True)
        yield from bps.kickoff(panda, wait=True)


def seq_table(
    start: float,
    stop: float,
    stepsize: float,
    time_per_point: float,
    motor: Motor,
    detectors: list[tuple[HDFPanda, int]],
    num_trajectory_points: int = 10,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
) -> MsgGenerator:
    # Generate triggers
    num_seqtable_repeats = 1
    if number_of_sweeps > 1:
        num_seqtable_repeats = mt.ceil(number_of_sweeps / 2)

    # Prepare motor
    num_seq_points = int((stop - start) / stepsize) + 1
    time_per_traj_point = (num_seq_points / num_trajectory_points) * time_per_point
    spec = Fly(
        time_per_traj_point
        @ (number_of_sweeps * ~Line(motor, start, stop, num_trajectory_points))
    )

    # Configure Panda
    detector_dict = {}
    for dets, seq_table_number in detectors:
        detector_dict[dets] = PandaScanConfig()
        match dets.name:
            case "panda1":
                # Generate triggers
                triggers = generate_position_triggers(
                    start=start,
                    stop=stop,
                    stepsize=stepsize,
                    number_of_sweeps=number_of_sweeps,
                )

                # Configure Sequence Table
                yield from prepare_seq_table(
                    triggers=triggers,
                    is_position_trigger=True,
                    add_sweep_triggers=add_sweep_triggers,
                    num_seqtable_repeats=num_seqtable_repeats,
                    panda=dets,
                    seq_table_number=seq_table_number,
                    detector_dict=detector_dict,
                )

            case "panda2":
                # Generate triggers
                triggers = generate_spectrum_triggers()

                # Configure Sequence Table
                yield from prepare_seq_table(
                    triggers=triggers,
                    is_spectrum_trigger=True,
                    num_seqtable_repeats=num_seqtable_repeats,
                    panda=dets,
                    seq_table_number=seq_table_number,
                    detector_dict=detector_dict,
                )

            case _:
                raise ValueError(f"{dets.name} is not a valid PandA for scanning")

    yield from seq_table_scan(
        scan_spec=spec, detector_dict=detector_dict, motor=motor, detectors=detectors
    )


def xas_scan(
    element: str,
    edge: str,
    duration: float,
    detectors: list[tuple[HDFPanda, int]],
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
) -> MsgGenerator:
    # Generate triggers
    params = XasScanParameters(element, edge)
    params.set_from_element_edge()
    params.set_abc_from_gaf()
    gen = XasScanPointGenerator(params)
    grid = gen.calculate_energy_time_grid()
    angle = energy_to_bragg_angle(si_111_lattice_spacing, grid[:, 0])

    # Configure Motor
    spec = Fly(duration @ (Line(motor, angle[0], angle[-1], len(angle))))

    # Configure Panda
    detector_dict = {}
    for dets, seq_table_number in detectors:
        detector_dict[dets] = PandaScanConfig()

        # Configure Sequence Table
        yield from prepare_seq_table(
            triggers=angle,
            is_position_trigger=True,
            num_seqtable_repeats=1,
            panda=dets,
            detector_dict=detector_dict,
            seq_table_number=seq_table_number,
        )

    # Run scan
    yield from seq_table_scan(
        scan_spec=spec, detector_dict=detector_dict, motor=motor, detectors=detectors
    )


# run_plan("seq_non_linear", ei=6000.0, ef=10000.0, de=100.0, duration=0.1)
def seq_non_linear(
    ei: float,
    ef: float,
    de: float,
    duration: float,
    detectors: list[tuple[HDFPanda, int]],
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
) -> MsgGenerator:
    # Generate triggers
    energies = np.arange(ei, ef + de, de)  # include Ef as last point in the array
    angle = energy_to_bragg_angle(si_111_lattice_spacing, energies)

    # Configure Motor
    spec = Fly(duration @ (Line(motor, angle[0], angle[-1], len(angle))))

    # Configure Panda
    detector_dict = {}
    for dets, seq_table_number in detectors:
        detector_dict[dets] = PandaScanConfig()

        # Configure Sequence Table
        yield from prepare_seq_table(
            triggers=angle,
            is_position_trigger=True,
            num_seqtable_repeats=1,
            panda=dets,
            detector_dict=detector_dict,
            seq_table_number=seq_table_number,
        )

    # Run scan
    yield from seq_table_scan(
        scan_spec=spec, detector_dict=detector_dict, motor=motor, detectors=detectors
    )


def seq_table_scan(
    scan_spec: Fly,
    motor: Motor,  # noqa: B008
    detector_dict: dict[HDFPanda, PandaScanConfig],
    detectors: list[tuple[HDFPanda, int]],
) -> MsgGenerator:
    dets = [panda for panda, _ in detectors]

    # Prepare PMAC
    pmac = turbo_slit_pmac(motor)
    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)

    yield from ensure_connected(pmac, motor)
    for panda, _ in detectors:
        yield from ensure_connected(panda)

    yield from setup_trajectory_scan_pvs()

    @bpp.stage_decorator([*dets])
    @bpp.run_decorator()
    def inner_plan():
        # Prepare pmac with the trajectory
        yield from bps.prepare(pmac_trajectory_flyer, scan_spec, wait=True)

        yield from prepare_pandas_for_scan(detector_dict)

        yield from bps.declare_stream(*dets, name="primary", collect=True)

        yield from kickoff_seqtables_and_pandas(detector_dict)

        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        yield from bps.collect_while_completing(
            flyers=[pmac_trajectory_flyer],
            dets=[*dets],
            stream_name="primary",
            flush_period=0.5,
        )

    yield from inner_plan()
