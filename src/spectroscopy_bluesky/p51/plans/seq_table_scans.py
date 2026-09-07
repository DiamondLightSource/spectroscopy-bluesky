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
    soft_signal_rw,
    SignalRW,
)
from ophyd_async.epics.motor import Motor
from ophyd_async.epics.pmac import (
    PmacTrajectoryTriggerLogic,
    PmacScanInfo,
)
import bluesky.plans as bp
from ophyd_async.fastcs.panda import (
    HDFPanda,
    SeqTable,
    SeqTableInfo,
    StaticSeqTableTriggerLogic,
)
from ophyd_async.epics.core import epics_signal_r
from ophyd_async.plan_stubs import ensure_connected
from scanspec.specs import Fly, Line
from collections.abc import Callable

from spectroscopy_bluesky.common.xas_scans import (
    XasScanParameters,
    XasScanPointGenerator,
)
from bluesky.preprocessors import (
    subs_decorator, 
    stub_decorator,
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

from typing import cast

from bluesky.callbacks.core import CollectThenCompute

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


from bluesky.callbacks.core import CollectThenCompute
from typing import cast

class ProcessData(CollectThenCompute):
    def __init__(self):
        super().__init__()
        self.processed_signal = Callable[[SignalRW], None]
        self.processed_signal_name = ""
        # PV configuration
        self.pv_min_threshold = 0
        self.pv_max_threshold = 0
        self.in_range = False
        self.pv_ensure_in_range = False
        # SNR calculations
        self.snr_db = 0
        self.pv_snr_min_threshold  = 0
        self.snr_in_range = False
        self.pv_compute_snr = False

    def start(self, doc):
        self.results = []
        self.reset()
        self.start_doc: dict = doc
        super().start(doc)

    def event(self, doc):
        # print(f"event received{doc}")
        # Check threshold hasnt been breached
        if self.pv_ensure_in_range and self.processed_signal_name in doc["data"]:
            value = doc["data"][self.processed_signal_name]
            # print(f"event received{doc}")
            # print(value)
            if value > self.pv_min_threshold and value <= self.pv_max_threshold:
                self.in_range = True
            else:
                self.in_range = False
        super().event(doc)


    def extract_data(self, dict_key):
        """Extract the x and y values (i.e. position of motor being
        moved and detector readout) from the event documents"""
        events = cast(dict, self._events)
        val = [e["data"][dict_key] for e in events if dict_key in e["data"]]
        timestamp = [
            e["timestamps"][dict_key] for e in events if dict_key in e["timestamps"]
        ]
        return val, timestamp

    def filter_average(self, dict_key, window):
        val, _ = self.extract_data(dict_key)
        return np.convolve(val, np.ones(window) / window, mode="same")

    def monitor_threshold(self, dict_key, threshold):
        val, _ = self.extract_data(dict_key)
        return any(x > threshold for x in val)

    def plot_data(self, val, timestamp, filename):
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 5))
        plt.plot(timestamp, val)
        plt.savefig(f"{filename}.png", dpi=300, bbox_inches="tight")
        plt.close()

    def suspend_plan(self, dict_key, threshold, **kwargs):
        val, _ = self.extract_data(dict_key)
        if np.any(val > threshold):
            print("Suspended atm")
            bps.pause()

    def compute(self):
        """This method is called at run-stop time by the superclass."""

        if self.pv_compute_snr:
            val, timestamp = self.extract_data(self.processed_signal_name)
            print(f"starting the scan analysis of {self.processed_signal_name}")

            from scipy.ndimage import gaussian_filter1d
            from scipy.signal import find_peaks

            filtered_data = gaussian_filter1d(val, sigma=2)

            peaks, props = find_peaks(
                filtered_data,
                prominence=1.0,
                distance=10
            )

            # Residual noise
            noise = np.array(val) - filtered_data

            # SNR calculation
            signal_rms = np.sqrt(np.sum(filtered_data**2))
            noise_rms = np.sqrt(np.sum(noise**2))

            # self.snr_db = 20 * np.log10(signal_rms / noise_rms)
            self.snr_db += 10

            print("Signal RMS =", signal_rms)
            print("Noise RMS =", noise_rms)
            print("SNR =", self.snr_db, "dB")

        # filtered_data = self.filter_average("motor_readback", 2)
        # self.plot_data(val, timestamp, "before_filter")
        # self.plot_data(filtered_data, timestamp, "after_filter")


def prepare_pv_monitoring(readable_pvs: dict[str, Any]) -> MsgGenerator:
    """
    Prepare and monitor EPICS process variables (PVs) from a configuration dictionary.

    This generator function iterates over a dictionary describing readable PVs,
    creates EPICS signal objects with the appropriate data types, ensures they are
    connected, and starts monitoring them.

    Args:
        readable_pvs : dict[str, Any]
            Dictionary defining PV configurations. Each value has the following keys:
                - "read_pv" (str): The EPICS PV identifier.
                - "pv_datatype" (str): The data type name (e.g., "float"), which is
                    mapped internally to a Python type.

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
    pvCallbacks = []
    for pv_name, pv_config in readable_pvs.items():
        datatype_str = pv_config["pv_datatype"].strip()
        if datatype_str not in datatype_map:
            raise ValueError(f"Unsupported datatype: {datatype_str}")
        datatype = datatype_map[datatype_str]

        pv_signal = epics_signal_r(
            datatype,
            pv_config["pv_name"].strip(),
            name=pv_name,
        )

        try:
            yield from ensure_connected(pv_signal)
        except Exception as e:
            raise RuntimeError(f"Failed to connect PV '{pv_name}'") from e
        
        pv_callback = ProcessData()
        pv_callback.processed_signal = pv_signal 
        pv_callback.processed_signal_name = pv_name
        pv_callback.pv_min_threshold = pv_config["pv_min_threshold"]
        pv_callback.pv_max_threshold = pv_config["pv_max_threshold"]
        pv_callback.pv_compute_snr = pv_config["pv_compute_snr"].lower() == "true" if isinstance(pv_config["pv_compute_snr"], str) else pv_config["pv_compute_snr"]
        pv_callback.pv_snr_min_threshold = pv_config["pv_snr_min_threshold"]
        pv_callback.pv_ensure_in_range = pv_config["pv_ensure_in_range"].lower() == "true" if isinstance(pv_config["pv_ensure_in_range"], str) else pv_config["pv_ensure_in_range"]
        pvCallbacks.append(pv_callback)

    return pvCallbacks


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
            yield from bps.prepare(panda, trigger_info, wait=True)
        yield from bps.prepare(seqtable_flyer, seq_table_info, wait=True)

        yield from bps.kickoff(seqtable_flyer, wait=True)
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

    scan_params_dict = {
        "scan_name": "seq_table_non_linear",
        "ei": ei,
        "ef": ef,
        "de": de,
        "readable_pvs": readable_pvs,
        "metadata": metadata,
    }

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
    panda: HDFPanda = inject("panda1"),  # noqa: B008,
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

    scan_params_dict = {
        "scan_name": "seq_table_energy_scan",
        "element": element,
        "edge": edge,
        "readable_pvs": readable_pvs,
        "metadata": metadata,
    }

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
    panda: HDFPanda = inject("panda1"),  # noqa: B008,
    panda2: HDFPanda = inject("panda2"),  # noqa: B008,
    num_trajectory_points: int = 10,
    triggers: list[TriggerSpec] | None = None,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
    readable_pvs: dict[str, Any] | None = None,
    ramp_time: float | None = None,
    turnaround_time: float | None = None,
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

    scan_params_dict = {
        "scan_name": "seq_table_two_panda_scan",
        "spectrum_triggers": spectrum_triggers,
        "metadata": metadata,
        "readable_pvs": readable_pvs,
    }

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
        ramp_time=ramp_time,
        turnaround_time=turnaround_time,
        metadata=metadata,
    )
      
def seq_table_uniform_scan(
    start: float,
    stop: float,
    stepsize: float,
    time_per_sweep: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda1"),  # noqa: B008,
    num_trajectory_points: int = 10,
    spectrum_triggers: list[TriggerSpec] | None = None,
    add_sweep_triggers: bool = False,
    number_of_sweeps: int = 4,
    ramp_time: float | None = None,
    turnaround_time: float | None = None,
    panda_dict: dict[HDFPanda, list[Callable[[], MsgGenerator]]] | None = None,
    readable_pvs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:

    capture_positions = np.arange(start, stop + 0.5 * stepsize, stepsize)
    # print(capture_positions)

    # setup a second seq table for 'spectrum based' triggering :
    if spectrum_triggers is not None:
        # initialise if nothing has been passed in
        if panda_dict is None:
            panda_dict = {}

        spectrumTriggers = generate_triggers(spectrum_triggers)
        seq_table = (
            SeqTableBuilder()
            .add_spectrum_based_triggers(spectrumTriggers)
            .get_seq_table()
        )

        prepare_triggers_seqtable = prepare_seq_table(
            panda, seq_table, 2, prepare_panda=False
        )
        panda_dict[panda] = [prepare_triggers_seqtable]

    scan_params_dict = {
        "scan_name": "seq_table_uniform_scan",
        "stepsize": stepsize,
        "spectrum_triggers": spectrum_triggers,
        "readable_pvs": readable_pvs,
        "metadata": metadata,
    }

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
        ramp_time=ramp_time,
        turnaround_time=turnaround_time,
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

    pv_callback = []
    # initialise if nothing has been passed in
    if panda_dict is None:
        panda_dict = {}

    def configure_scan_parameters(
        n: int | None = None
    ):  
        time_per_traj_point = time_per_sweep / num_trajectory_points

        print(
            f"Num trajectorypoints : {num_trajectory_points}, "
            f"time per traj point : {time_per_traj_point}",
            f"step: {len(capture_positions)}"
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

        stream_name = f"primary{n}"
        kwargs["scan_params_dict"].update(
            {
                "start": start,
                "stop": stop,
                "time_per_sweep": time_per_sweep,
                "capture_positions": capture_positions,
                "motor": motor,
                "panda": panda,
                "num_trajectory_points": num_trajectory_points,
                "add_sweep_triggers": add_sweep_triggers,
                "number_of_sweeps": number_of_sweeps,
                "time_per_traj_point": time_per_traj_point,
                "num_seqtable_repeats": num_seqtable_repeats,
                "pv_callback":pv_callback,
                "stream_name":stream_name,
            }
        )
        yield from seq_table_scan(scan_spec, panda_dict, motor=motor, **kwargs)

    scan_parameters = kwargs.get("scan_params_dict") or {}
    readable_pvs = scan_parameters.get("readable_pvs") or {}

    if readable_pvs is not None:
        pv_callback = yield from prepare_pv_monitoring(readable_pvs)
        n = 0
        
        if not any(pvs.pv_compute_snr for pvs in pv_callback):
            print("Not an adaptive scan")
            yield from configure_scan_parameters(n) 
        else:
            yield from bps.checkpoint()
            while all(pvs.snr_db <= pvs.pv_snr_min_threshold for pvs in pv_callback if pvs.pv_compute_snr):
                print("Adaptive Scan: snr is not in range")
                yield from configure_scan_parameters(n) 
                n += 1
                time_per_sweep += 1
                # stepsize = stepsize*2
                if not all(pvs.in_range for pvs in pv_callback if pvs.pv_ensure_in_range):
                    print("Scan parameters not in range")
                    yield from bps.deferred_pause()
                    break    
    else:
        print ("Not monitoring PVs")
        yield from configure_scan_parameters() 


def seq_table_scan(
    scan_spec: Fly,
    panda_dict: dict[
        HDFPanda, list[Callable[[], MsgGenerator]]
    ],  # dict containing functions to prepare each panda
    motor: Motor,
    **kwargs: Any,
) -> MsgGenerator:
    pmac = turbo_slit_pmac(motor)

    yield from ensure_connected(pmac, motor)
    yield from setup_trajectory_scan_pvs()

    detectors = panda_dict.keys()
    for detector in detectors:
        yield from ensure_connected(detector)

    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)  # pyright: ignore[reportArgumentType]
    pamc_trigger_logic = PmacScanInfo(
        spec=scan_spec,
        ramp_time=kwargs.get("ramp_time") or None,
        turnaround_time=kwargs.get("turnaround_time") or None,
    )

    scan_parameters = kwargs.get("scan_params_dict") or {}
    scan_name = scan_parameters.get("scan_name")
    pv_callback = scan_parameters.get("pv_callback") or {}
    stream_name = scan_parameters.get("stream_name")

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

    # Define soft signal to add processed data
    initial_value = np.array([0.1, 10.2], dtype=np.float64)
    softSignal = soft_signal_rw(
        Array1D[np.float64], initial_value=initial_value, name="processed_val"
    )
    process_motor_data = ProcessData()
    process_motor_data.processed_signal = softSignal  # pyright: ignore

    def retrieve_tiled_data():
        from blueapi.service.authentication import TiledAuth
        from blueapi.service.interface import context
        from tiled.client import from_uri
        from tiled.queries import Key

        tiled_config = context().tiled_conf
        tiled_client = from_uri(
            str(tiled_config.url),
            auth=TiledAuth(tiled_auth=tiled_config.authentication),
        )
        result = tiled_client.search(
            Key("start.instrument_session") == "cm44254-1"
        ).search(Key("start.plan_name") == "seq_table_uniform_scan")
        scanData = result.values().last()
        for key, data in scanData.items():
            # Still running into read error with Panda HDF data so excluding it for now
            if key != "primary2":
                for key, data2 in data.items():
                    # Print actual data
                    print(key, data2.read())
        
        # randArray = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        # yield from bps.abs_set(softSignal, randArray, wait=True)
        yield from bps.sleep(1)

    def append_processed_data():
        yield from bps.monitor(softSignal, name="processed")
        averaged_softSignal = process_softSignal.filter_average(
            dict_key="motor_readback", window=5
        )
        yield from bps.abs_set(softSignal, averaged_softSignal, wait=True)

        randArray = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
        yield from bps.abs_set(softSignal, randArray, wait=True)
        threshold_exceeded = process_softSignal.monitor_threshold(
                dict_key="motor_readback", threshold=9.79382
            )
        if threshold_exceeded:
            yield from inner_squared_plan()


    @stub_decorator()
    def inner_squared_plan():
        for pvs in pv_callback:
            if pvs.pv_ensure_in_range:
                yield from bps.monitor(pvs.processed_signal, name=pvs.processed_signal_name) 
        while not all(pvs.in_range for pvs in pv_callback if pvs.pv_ensure_in_range):
            yield from bps.sleep(0.1)
        yield from bp.count([motor], 20)    

    @stub_decorator()
    def inner_plan():
        yield from bps.prepare(pmac_trajectory_flyer, pamc_trigger_logic, wait=True)

        # prepare and kickoff panda seq tables
        for preparer_funcs in panda_dict.values():
            for prepare in preparer_funcs:
                yield from prepare()

        yield from bps.declare_stream(*detectors, name = stream_name, collect=True)

        for panda in detectors:
            yield from bps.kickoff(panda)

        # Prepare pmac with the trajectory
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        # Monitor the rest of the PVs         
        for pvs in pv_callback:
            if not pvs.pv_ensure_in_range:
                yield from bps.monitor(pvs.processed_signal, name=pvs.processed_signal_name)   

        yield from bps.collect_while_completing(
            flyers=[pmac_trajectory_flyer],
            dets=[*detectors],
            stream_name= stream_name,
            flush_period=0.5,
        )

    @subs_decorator(pv_callback)
    @bpp.stage_decorator([*detectors])
    @bpp.run_decorator(md=_md)
    def combined_plan():
        from datetime import datetime

        current_time = datetime.now().strftime("%H:%M:%S")
        print("Current time:", current_time)
        yield from inner_squared_plan()
        yield from inner_plan()

        # yield from inner_plan()
        # yield from append_processed_data()
        # yield from retrieve_tiled_data()

    yield from combined_plan()
    print("end of plan")