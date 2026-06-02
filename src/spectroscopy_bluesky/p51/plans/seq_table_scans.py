import math as mt  # noqa: I001
from typing import Any
import logging
from collections.abc import Sequence
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
    EnumTypes,
    Array1D,
    Table,
    StrictEnum,
    SubsetEnum,
    SupersetEnum,
)
from ophyd_async.epics.motor import Motor
from ophyd_async.epics.pmac import (
    PmacTrajectoryTriggerLogic,
    PmacScanInfo,
)
from ophyd_async.fastcs.panda import (
    HDFPanda,
    SeqTable,
    SeqTableInfo,
    StaticSeqTableTriggerLogic,
)
from ophyd_async.epics.core import epics_signal_r
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Fly, Line, Concat, Product
from collections.abc import Callable

from spectroscopy_bluesky.common.xas_scans import (
    XasScanParameters,
    XasScanPointGenerator,
)

from spectroscopy_bluesky.common.quantity_conversion import (
    si_111_lattice_spacing,
    energy_to_bragg_angle,
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


# output_ports, pulse_width, output_delay, num_repeats, type, trigger_repeat
TriggerSpec = tuple[list[int], float, float, int, int, int]


def generate_triggers(
    triggers: list[TriggerSpec],
) -> list[SpectrumBasedTrigger]:
    spectrum_triggers = []
    for (
        output_ports,
        pulse_width,
        output_delay,
        output_num_repeats,
        trigger_type,
        trigger_repeat,
    ) in triggers:
        for _ in range(trigger_repeat):
            spectrum_triggers.append(
                SpectrumBasedTrigger(
                    spectrum_number=1,
                    trigger_type=SpectrumTriggerType(trigger_type),
                    output_ports=output_ports,
                    output_length=pulse_width,
                    output_delay=output_delay,
                    output_num_repeats=output_num_repeats,
                )
            )

    return spectrum_triggers


LOGGER = logging.getLogger(__name__)


def log_scan_parameters(**kwargs) -> dict:
    return kwargs


def prepare_pvs(readable_pvs: dict[str, Any]) -> MsgGenerator:
    """
    Prepare and monitor EPICS process variables (PVs) from a configuration dictionary.

    This generator function iterates over a dictionary describing readable PVs,
    creates EPICS signal objects with the appropriate data types, ensures they are
    connected, and starts monitoring them.

    Args:
        readable_pvs : dict[str, Any]
            Dictionary defining PV configurations. Each value has the following keys:
                - "pv_name" (str): The EPICS PV identifier.
                - "datatype" (str): The data type name (e.g., "float"), which is mapped
                internally to a Python type.

    Returns:
        MsgGenerator


    Notes:
    - Currently supports a limited set of data types via `datatype_map`.
    """
    datatype_map = {
        "bool": bool,
        "int": int,
        "float": float,
        "str": str,
        "EnumTypes": EnumTypes,
        "Array1D[np.bool_]": Array1D[np.bool_],
        "Array1D[np.int8]": Array1D[np.int8],
        "Array1D[np.uint8]": Array1D[np.uint8],
        "Array1D[np.int16]": Array1D[np.int16],
        "Array1D[np.uint16]": Array1D[np.uint16],
        "Array1D[np.int32]": Array1D[np.int32],
        "Array1D[np.uint32]": Array1D[np.uint32],
        "Array1D[np.int64]": Array1D[np.int64],
        "Array1D[np.uint64]": Array1D[np.uint64],
        "Array1D[np.float32]": Array1D[np.float32],
        "Array1D[np.float64]": Array1D[np.float64],
        "np.ndarray": np.ndarray,
        "Sequence[str]": Sequence[str],
        "Sequence[StrictEnum]": Sequence[StrictEnum],
        "Sequence[SubsetEnum]": Sequence[SubsetEnum],
        "Sequence[SupersetEnum]": Sequence[SupersetEnum],
        "Table": Table,
    }
    for pv_key, pv_config in readable_pvs.items():
        datatype_str = pv_config["pv_datatype"].strip()
        if datatype_str not in datatype_map:
            raise ValueError(f"Unsupported datatype: {datatype_str}")
        datatype = datatype_map[datatype_str]

        pv_signal = epics_signal_r(
            datatype,
            pv_config["pv_name"].strip(),
            name=pv_key,
        )

        try:
            yield from ensure_connected(pv_signal)
        except Exception as e:
            raise RuntimeError(f"Failed to connect PV '{pv_key}'") from e

        yield from bps.monitor(pv_signal, name=pv_key)


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
    number_of_sweeps: int = 1,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    # Start the plan by loading the saved design for this scan

    energies = np.arange(ei, ef + de, de)  # include Ef as last point in the array
    print(f"param\nEi = {ei}, Ef = {ef}, dE = {de}\n")

    angle = energy_to_bragg_angle(si_111_lattice_spacing, energies)

    scan_params_dict = log_scan_parameters(
        scan_name="seq_table_non_linear",
        ei=ei,
        ef=ef,
        de=de,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )
    yield from seq_table_position_scan(
        angle[0],
        angle[-1],
        time_per_sweep,
        angle,
        motor,
        panda,
        num_trajectory_points=len(angle),
        number_of_sweeps=number_of_sweeps,
        scan_params_dict=scan_params_dict,
    )


def seq_table_energy_scan(
    element: str,
    edge: str,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    number_of_sweeps: int = 1,
    variable_exafs_time: bool = False,
    ramp_time: float | None = None,
    turnaround_time: float | None = None,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    prescale_as_us = 1
    # Generate triggers
    params = XasScanParameters(element, edge)
    params.set_from_element_edge()
    params.set_abc_from_gaf()
    if variable_exafs_time:
        params.exafsTimeType = "variable time"
        prescale_as_us = 10
    gen = XasScanPointGenerator(params)
    grid = gen.calculate_energy_time_grid()
    angle = energy_to_bragg_angle(si_111_lattice_spacing, grid[:, 0])
    capture_time = None
    if variable_exafs_time:
        capture_time = grid[:, 1] * prescale_as_us

    scan_params_dict = log_scan_parameters(
        scan_name="seq_table_energy_scan",
        element=element,
        edge=edge,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )
    yield from seq_table_position_scan(
        angle[0],
        angle[-1],
        time_per_sweep,
        angle,
        motor,
        panda,
        num_trajectory_points=len(angle),
        capture_time=capture_time,
        number_of_sweeps=number_of_sweeps,
        scan_params_dict=scan_params_dict,
    )


def seq_table_two_panda_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    panda2: HDFPanda = inject("panda2"),  # noqa: B008
    num_trajectory_points: int = 10,
    triggers: list[TriggerSpec] | None = None,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
    ramp_time: float | None = None,
    turnaround_time: float | None = None,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    # setup a second seq table for 'spectrum based' triggering
    panda_dict = {}
    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)
    if triggers is not None:
        spectrum_triggers = generate_triggers(triggers)
        seq_table = (
            SeqTableBuilder()
            .add_spectrum_based_triggers(spectrum_triggers)
            .get_seq_table()
        )
        num_seqtable_repeats = 1
        if number_of_sweeps > 1:
            num_seqtable_repeats = mt.ceil(number_of_sweeps / 2)

        prepare_triggers_seqtable = prepare_seq_table(
            panda2, seq_table, 1, num_seqtable_repeats
        )
        panda_dict[panda2] = [prepare_triggers_seqtable]

    scan_params_dict = log_scan_parameters(
        scan_name="seq_table_two_panda_scan",
        spectrum_triggers=triggers,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )

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
        scan_params_dict=scan_params_dict,
    )


def panda_step_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    num_trajectory_points: int = 10,
    number_of_sweeps: int = 4,
    add_sweep_triggers: bool = False,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    time_per_traj_point = time_per_sweep / num_trajectory_points
    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)
    print(
        f"Num trajectorypoints : {num_trajectory_points}, "
        f"time per traj point : {time_per_traj_point}"
    )

    scan_spec = time_per_traj_point @ (
        number_of_sweeps * ~Line(motor, start, stop, num_trajectory_points)
    )

    yield from seq_table_position_scan(
        start,
        stop,
        time_per_sweep,
        capture_positions,
        motor,
        panda,
        num_trajectory_points,
        add_sweep_triggers,
        number_of_sweeps,
        scan_spec=scan_spec,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )


def variable_motor_speed_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    velocity: list[float],
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    num_trajectory_points: int = 10,
    number_of_sweeps: int = 4,
    add_sweep_triggers: bool = False,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)
    new_number_of_sweeps = mt.ceil(number_of_sweeps / len(velocity))
    spec = Fly(
        velocity[0]
        @ Product(
            new_number_of_sweeps,
            ~Line(motor, start, stop, num_trajectory_points),
            gap=True,
        )
    )
    for vel in velocity[1:]:
        spec2 = Fly(
            vel
            @ Product(
                new_number_of_sweeps,
                ~Line(motor, start, stop, num_trajectory_points),
                gap=True,
            )
        )
        temp_spec = Concat(spec, spec2, gap=True)
        spec = temp_spec

    # print(spec)
    # print(f"spec.frames()[x].gap() = {spec.frames().gap}")
    # print(f"spec.frames()[x].midpoints() = {spec.frames().midpoints}")

    yield from seq_table_position_scan(
        start,
        stop,
        time_per_sweep,
        capture_positions,
        motor,
        panda,
        num_trajectory_points,
        add_sweep_triggers,
        number_of_sweeps,
        scan_spec=spec,
        ramp_time=0,
        turnaround_time=0.02,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )


def configurable_rampup_turnaround(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    num_trajectory_points: int = 10,
    number_of_sweeps: int = 4,
    ramp_time: float | None = None,
    turnaround_time: float | None = None,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    yield from seq_table_uniform_scan(
        start,
        stop,
        stepsize,
        time_per_sweep,
        motor,
        panda,
        num_trajectory_points,
        number_of_sweeps=number_of_sweeps,
        ramp_time=ramp_time,
        turnaround_time=turnaround_time,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )


def seq_table_uniform_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    num_trajectory_points: int = 10,
    spectrum_triggers: list[TriggerSpec] | None = None,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
    panda_dict: dict[HDFPanda, list[Callable[[], MsgGenerator]]] | None = None,
    ramp_time: float | None = None,
    turnaround_time: float | None = None,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:

    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)

    # setup a second seq table for 'spectrum based' triggering :
    if panda_dict is None:
        panda_dict = {}
    if spectrum_triggers is not None:
        spectrumtriggers = generate_triggers(spectrum_triggers)
        seq_table = (
            SeqTableBuilder()
            .add_spectrum_based_triggers(spectrumtriggers)
            .get_seq_table()
        )

        prepare_triggers_seqtable = prepare_seq_table(
            panda, seq_table, 2, prepare_panda=False
        )
        panda_dict[panda] = [prepare_triggers_seqtable]

    scan_params_dict = log_scan_parameters(
        scan_name="seq_table_uniform_scan",
        stepsize=stepsize,
        spectrum_triggers=spectrum_triggers,
        readable_pvs=readable_pvs,
        metadata=metadata,
    )

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
        scan_params_dict=scan_params_dict,
    )


def seq_table_position_scan(
    start: float,
    stop: float,
    time_per_sweep: float,
    capture_positions: NDArray,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008
    num_trajectory_points: int = 10,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
    panda_dict: dict[HDFPanda, list[Callable[[], MsgGenerator]]] | None = None,
    capture_time: list[float] | None = None,
    prescale_as_us: float = 1,
    scan_spec: Fly | None = None,
    **kwargs: Any,
) -> MsgGenerator:
    if scan_spec is None:
        time_per_traj_point = time_per_sweep / num_trajectory_points

        print(
            f"Num trajectorypoints : {num_trajectory_points}, "
            f"time per traj point : {time_per_traj_point}"
        )
        scan_spec = Fly(
            time_per_traj_point
            @ (number_of_sweeps * ~Line(motor, start, stop, num_trajectory_points))
        )

    # add points to capture positions on the reverse sweep
    if number_of_sweeps > 1:
        num_captures = capture_positions.size
        positions = np.zeros(2 * num_captures)
        positions[0:num_captures] = capture_positions
        positions[num_captures : num_captures * 2] = np.flip(capture_positions)
        time = np.zeros(2 * num_captures)
        if capture_time is not None:
            time[0:num_captures] = capture_time
            time[num_captures : num_captures * 2] = np.flip(capture_time)
    else:
        positions = capture_positions
        time = capture_time

    num_seqtable_repeats = 1
    if number_of_sweeps > 1:
        num_seqtable_repeats = mt.ceil(number_of_sweeps / 2)

    # Sequence table has position triggers for one back-and-forth sweep.
    # Use multiple repetitions of seq table to capture subsequent sweeps.
    seqTable_builder = SeqTableBuilder()
    seqTable_builder.convert_to_encoder = get_encoder_counts
    if capture_time is None:
        seqTable_builder.add_positions(
            positions, time1=1, outa1=True, time2=1, outa2=False
        )
    else:
        seqTable_builder.add_variable_positions(
            positions, time=time, outa1=True, outa2=False
        )
    if add_sweep_triggers:
        seqTable_builder.add_start_end_triggers("outb1", "outc1")

    # initialise if nothing has been passed in
    if panda_dict is None:
        panda_dict = {}

    prepare_position_seqtable = prepare_seq_table(
        panda,
        seqTable_builder.get_seq_table(),
        1,
        num_seqtable_repeats,
        prescale_as_us=prescale_as_us,
    )
    # append position sequence table setup to panda entry (make empty list first
    # if not already present).
    panda_dict.setdefault(panda, []).append(prepare_position_seqtable)

    if kwargs.get("scan_params_dict") is None:
        kwargs["scan_params_dict"] = {}
        kwargs["scan_params_dict"]["scan_name"] = "seq_table_position_scan"

    kwargs["scan_params_dict"].update(
        log_scan_parameters(
            start=start,
            stop=stop,
            time_per_sweep=time_per_sweep,
            capture_positions=capture_positions,
            motor=motor,
            panda=panda,
            num_trajectory_points=num_trajectory_points,
            add_sweep_triggers=add_sweep_triggers,
            number_of_sweeps=number_of_sweeps,
            num_seqtable_repeats=num_seqtable_repeats,
        )
    )

    yield from seq_table_scan(scan_spec, panda_dict, motor=motor, **kwargs)


def seq_table_scan(
    scan_spec: Fly,
    panda_dict: dict[
        HDFPanda, list[Callable[[], MsgGenerator]]
    ],  # dict containing functions to prepare each panda
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    **kwargs: Any,
) -> MsgGenerator:
    pmac = turbo_slit_pmac(motor)

    yield from ensure_connected(pmac, motor)
    yield from setup_trajectory_scan_pvs()

    detectors = panda_dict.keys()
    for detector in detectors:
        yield from ensure_connected(detector)

    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)
    pamc_trigger_logic = PmacScanInfo(
        spec=scan_spec,
        ramp_time=kwargs.get("ramp_time"),
        turnaround_time=kwargs.get("turnaround_time"),
    )

    scan_parameters = kwargs.get("scan_params_dict") or {}
    scan_name = scan_parameters.get("scan_name")

    _md = {
        "plan_args": {
            "detectors": {det.name for det in detectors},
            "spec": repr(scan_spec),
            "motor": repr(motor),
            **{
                k: repr(v) if not isinstance(v, np.ndarray) else v
                for k, v in scan_parameters.items()
            },
        },
    }

    # Log scan name and parameters
    LOGGER.info(f"Running {scan_name} plan with scan parameters {scan_parameters}")

    @bpp.stage_decorator([*detectors])
    @bpp.run_decorator(md=_md)
    def inner_plan():
        yield from bps.prepare(pmac_trajectory_flyer, pamc_trigger_logic, wait=True)

        # prepare and kickoff panda seq tables
        for preparer_funcs in panda_dict.values():
            for prepare in preparer_funcs:
                yield from prepare()

        yield from bps.declare_stream(*detectors, name="primary", collect=True)

        for panda in detectors:
            yield from bps.kickoff(panda)

        # Prepare pmac with the trajectory
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        if scan_parameters.get("readable_pvs") is not None:
            yield from prepare_pvs(scan_parameters["readable_pvs"])

        yield from bps.collect_while_completing(
            flyers=[pmac_trajectory_flyer],
            dets=[*detectors],
            stream_name="primary",
            flush_period=0.5,
        )

    yield from inner_plan()
