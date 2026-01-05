import asyncio
import math as mt
from itertools import pairwise

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from aioca import caput
from bluesky.utils import MsgGenerator
from dodal.beamlines.i20_1 import turbo_slit_pmac
from dodal.common.coordination import inject
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator
from numpy.typing import NDArray
from ophyd_async.core import (
    DetectorTrigger,
    FlyMotorInfo,
    StandardFlyer,
    TriggerInfo,
    YamlSettingsProvider,
    wait_for_value,
)
from ophyd_async.epics.core import epics_signal_rw
from ophyd_async.epics.motor import Motor
from ophyd_async.epics.pmac import (
    PmacTrajectoryTriggerLogic,
)
from ophyd_async.fastcs.panda import (
    HDFPanda,
    PandaPcompDirection,
    PcompInfo,
    SeqTable,
    SeqTableInfo,
    SeqTrigger,
    StaticPcompTriggerLogic,
    StaticSeqTableTriggerLogic,
)
from ophyd_async.fastcs.panda._block import PcompBlock
from ophyd_async.plan_stubs import (
    apply_panda_settings,
    ensure_connected,
    retrieve_settings,
    store_settings,
)
from scanspec.specs import Fly, Line

from spectroscopy_bluesky.common.quantity_conversion import (
    energy_to_bragg_angle,
    si_111_lattice_spacing,
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


class _StaticPcompTriggerLogic(StaticPcompTriggerLogic):
    """For controlling the PandA `PcompBlock` when flyscanning."""

    def __init__(self, pcomp: PcompBlock) -> None:
        self.pcomp = pcomp

    async def kickoff(self) -> None:
        await wait_for_value(self.pcomp.active, True, timeout=1)

    async def prepare(self, value: PcompInfo) -> None:
        await caput("BL20J-EA-PANDA-02:SRGATE1:FORCE_RST", "1", wait=True)
        await asyncio.gather(
            self.pcomp.start.set(value.start_postion),
            self.pcomp.width.set(value.pulse_width),
            self.pcomp.step.set(value.rising_edge_step),
            self.pcomp.pulses.set(value.number_of_pulses),
            self.pcomp.dir.set(value.direction),
        )

    async def stop(self):
        pass


def calculate_stuff(start, stop, num):
    width = (stop - start) / (num - 1)
    direction_of_sweep = (
        PandaPcompDirection.POSITIVE
        if get_encoder_counts(width, 0) > 0
        else PandaPcompDirection.NEGATIVE
    )

    return width, start, stop, direction_of_sweep


def get_pcomp_info(width, start_pos, direction_of_sweep: PandaPcompDirection, num):
    start_pos_pcomp = mt.floor(get_encoder_counts(start_pos))
    rising_edge_step = mt.ceil(abs(get_encoder_counts(width, 0)))

    panda_pcomp_info = PcompInfo(
        start_postion=start_pos_pcomp,
        pulse_width=1,
        rising_edge_step=rising_edge_step,
        number_of_pulses=num,
        direction=direction_of_sweep,
    )

    return panda_pcomp_info


def setup_trajectory_scan_pvs(prefix: str = "BL20J-MO-STEP-06"):
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


def fly_scan_ts(
    start: int,
    stop: int,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
) -> MsgGenerator:
    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        width = (stop - start) / (num - 1)
        start_pos = start - (width / 2)
        stop_pos = stop + (width / 2)
        motor_info = FlyMotorInfo(
            start_position=start_pos,
            end_position=stop_pos,
            time_for_move=num * duration,
        )
        panda_pcomp_info = PcompInfo(
            start_postion=mt.ceil(get_encoder_counts(start_pos)),
            pulse_width=1,
            rising_edge_step=mt.ceil(abs(get_encoder_counts(width, 0))),
            number_of_pulses=num,
            direction=PandaPcompDirection.POSITIVE
            if get_encoder_counts(width) > 0
            else PandaPcompDirection.NEGATIVE,
        )

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.CONSTANT_GATE,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(motor, motor_info)
        yield from bps.prepare(panda, panda_hdf_info)
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)
        yield from bps.kickoff(panda)
        yield from bps.kickoff(panda_pcomp, wait=True)
        yield from bps.kickoff(motor, wait=True)
        yield from bps.complete_all(motor, panda_pcomp, panda, wait=True)

    yield from inner_plan()


def fly_sweep(
    start: float,
    stop: float,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
    number_of_sweeps: int = 5,
    runup: float = 0.0,
) -> MsgGenerator:
    panda_pcomp = StandardFlyer(StaticPcompTriggerLogic(panda.pcomp[1]))

    def inner_squared_plan(start: float | int, stop: float | int):
        width, start_pos, stop_pos, direction_of_sweep = calculate_stuff(
            start, stop, num
        )

        direction_multiplier = -1.0
        if start < stop:
            direction_multiplier = 1.0

        motor_info = FlyMotorInfo(
            # include extra runup distance on start and end positions
            start_position=start_pos - direction_multiplier * runup,
            end_position=stop_pos + direction_multiplier * runup,
            time_for_move=num * duration,
        )

        panda_pcomp_info = get_pcomp_info(width, start_pos, direction_of_sweep, num)

        # move motor to initial position
        yield from bps.prepare(motor, motor_info, wait=True)

        # prepare pcomp
        yield from bps.prepare(panda_pcomp, panda_pcomp_info, wait=True)
        yield from bps.kickoff(panda_pcomp, wait=True)

        # kickoff motor move once pcomp has started
        yield from bps.kickoff(motor, wait=True)

        yield from bps.complete_all(motor, panda_pcomp, wait=True)

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp])
    def inner_plan():
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
        yield from bps.kickoff(panda, wait=True)

        for n in range(number_of_sweeps):
            even: bool = n % 2 == 0
            start2, stop2 = (start, stop) if even else (stop, start)
            print(f"Starting sweep {n} with start: {start2}, stop: {stop2}")
            yield from inner_squared_plan(start2, stop2)
            print(f"Completed sweep {n}")

        yield from bps.complete_all(panda, wait=True)

    panda_hdf_info = TriggerInfo(
        number_of_events=num * number_of_sweeps,
        trigger=DetectorTrigger.CONSTANT_GATE,
        livetime=duration,
        deadtime=1e-5,
    )

    yield from inner_plan()


def fly_sweep_both_ways(
    start: float,
    stop: float,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
    number_of_sweeps: int = 5,
) -> MsgGenerator:
    panda_pcomp1 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[1]))
    panda_pcomp2 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[2]))

    def inner_squared_plan(start: float, stop: float, panda_pcomp: StandardFlyer):
        motor_info = FlyMotorInfo(
            # include extra runup distance on start and end positions
            start_position=start,
            end_position=stop,
            time_for_move=num * duration,
        )

        # move motor to initial position
        yield from bps.prepare(motor, motor_info, wait=True)

        # kickoff motor move once pcomp has started
        yield from bps.kickoff(motor, wait=True)

        yield from bps.complete_all(motor, panda_pcomp, wait=True)

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp1, panda_pcomp2])
    def inner_plan():
        width, _, _, direction_of_sweep = calculate_stuff(start, stop, num)

        dir1 = direction_of_sweep
        dir2 = (
            PandaPcompDirection.POSITIVE
            if direction_of_sweep == PandaPcompDirection.NEGATIVE
            else PandaPcompDirection.NEGATIVE
        )

        pcomp_info1 = get_pcomp_info(width, start, dir1, num)

        pcomp_info2 = get_pcomp_info(width, stop, dir2, num)

        motor_info = FlyMotorInfo(
            # include extra runup distance on start and end positions
            start_position=start,
            end_position=stop,
            time_for_move=num * duration,
        )

        yield from bps.prepare(motor, motor_info, wait=True)

        # prepare both pcomps
        yield from bps.prepare(panda_pcomp1, pcomp_info1, wait=True)
        yield from bps.prepare(panda_pcomp2, pcomp_info2, wait=True)

        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)
        yield from bps.kickoff(panda, wait=True)

        for n in range(number_of_sweeps):
            even: bool = n % 2 == 0
            start2, stop2 = (start, stop) if even else (stop, start)
            panda_pcomp = panda_pcomp1
            if not even:
                panda_pcomp = panda_pcomp2
            print(f"Starting sweep {n} with start: {start2}, stop: {stop2}")
            yield from inner_squared_plan(start2, stop2, panda_pcomp)
            print(f"Completed sweep {n}")

        yield from bps.complete_all(panda, wait=True)

    panda_hdf_info = TriggerInfo(
        number_of_events=num * number_of_sweeps,
        trigger=DetectorTrigger.CONSTANT_GATE,
        livetime=duration,
        deadtime=1e-5,
    )

    yield from inner_plan()


def trajectory_fly_scan(
    start: float,
    stop: float,
    num: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
    restore: bool = False,
) -> MsgGenerator:
    # Start the plan by loading the saved design for this scan
    if restore:
        yield from plan_restore_settings(panda=panda, name="pcomp_auto_reset")

    panda_pcomp1 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[1]))
    panda_pcomp2 = StandardFlyer(_StaticPcompTriggerLogic(panda.pcomp[2]))
    pmac = turbo_slit_pmac()

    yield from ensure_connected(pmac, motor)

    yield from setup_trajectory_scan_pvs()

    spec = Fly(float(duration) @ (Line(motor, start, stop, num)))

    trigger_logic = spec
    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_pcomp1, panda_pcomp2])
    def inner_plan():
        width, _, _, direction_of_sweep = calculate_stuff(start, stop, num)

        dir1 = direction_of_sweep
        dir2 = (
            PandaPcompDirection.POSITIVE
            if direction_of_sweep == PandaPcompDirection.NEGATIVE
            else PandaPcompDirection.NEGATIVE
        )

        pcomp_info1 = get_pcomp_info(width, start, dir1, num)
        pcomp_info2 = get_pcomp_info(width, stop, dir2, num)

        panda_hdf_info = TriggerInfo(
            number_of_events=num,
            trigger=DetectorTrigger.CONSTANT_GATE,
            livetime=duration,
            deadtime=1e-5,
        )

        yield from bps.prepare(pmac_trajectory_flyer, trigger_logic, wait=True)
        # prepare both pcomps
        yield from bps.prepare(panda_pcomp1, pcomp_info1, wait=True)
        yield from bps.prepare(panda_pcomp2, pcomp_info2, wait=True)
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)

        yield from bps.kickoff(panda, wait=True)
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        yield from bps.complete_all(pmac_trajectory_flyer, panda, wait=True)

    yield from inner_plan()


def seq_table(
    start: float,
    stop: float,
    num_readouts: int,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
    number_of_sweeps: int = 3,
    restore: bool = False,
) -> MsgGenerator:
    # Prepare motor info using trajectory scanning
    spec = Fly(duration @ (number_of_sweeps * ~Line(motor, start, stop, num_readouts)))

    positions = spec.frames().lower[motor]

    # Sequence table has position triggers for one back-and-forth sweep.
    # Use multiple repetitions of sequence table to capture subsequent sweeps.
    num_repeats = 1
    if number_of_sweeps > 2:
        positions = positions[: 2 * num_readouts]
        num_repeats = mt.ceil(number_of_sweeps / 2)

    table = create_seqtable(positions, time1=1, outa1=True, time2=1, outa2=False)

    seq_table_info = SeqTableInfo(
        sequence_table=table, repeats=num_repeats, prescale_as_us=1
    )

    yield from seq_table_scan(
        spec, seq_table_info, motor=motor, panda=panda, restore=restore
    )


# run_plan("seq_non_linear", ei=6000.0, ef=10000.0, de=100.0, duration=0.1)
def seq_non_linear(
    ei: float,
    ef: float,
    de: float,
    duration: float,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
    restore: bool = False,
) -> MsgGenerator:
    # Start the plan by loading the saved design for this scan

    energies = np.arange(ei, ef + de, de)  # include Ef as last point in the array
    print(f"param\nEi = {ei}, Ef = {ef}, dE = {de}\n")

    angle = energy_to_bragg_angle(si_111_lattice_spacing, energies)

    # Prepare motor info using trajectory scanning
    spec = Fly(duration @ (Line(motor, angle[0], angle[-1], len(angle))))

    table = create_seqtable(
        angle, time1=1, time2=1, outa1=True, outb1=True, outa2=False, outb2=True
    )
    seq_table_info = SeqTableInfo(sequence_table=table, repeats=1, prescale_as_us=1)

    yield from seq_table_scan(spec, seq_table_info, motor, panda, restore=restore)


def create_seqtable(positions: NDArray, **kwargs) -> SeqTable:
    """
    Create SeqTable with rows setup to do position based triggering.

    <li> Each position in positions NDArray is converted to a row of the sequence table.
    <li> Position values are converted to encoder counts using
        'get_encoder_counts' function.
    <li> SeqTrigger direction set to GT or LT depending on when encoder values
        increase or decrease.

    :param positions: positions in user coordinates.
    :param kwargs: additional kwargs to be used when generating each
    row of sequence table (e.g. for setting trigger outputs, trigger length etc.)
    :return: SeqTable
    """

    # convert user positions to encoder positions
    enc_count_positions = [get_encoder_counts(x).astype(int) for x in positions]

    # determine direction of each segment
    direction = [
        SeqTrigger.POSA_GT if current < next else SeqTrigger.POSA_LT
        for current, next in pairwise(enc_count_positions)
    ]
    direction.append(direction[-1])

    table = SeqTable()
    for d, p in zip(direction, enc_count_positions, strict=True):
        table += SeqTable.row(repeats=1, trigger=d, position=p, **kwargs)
    return table


def seq_table_scan(
    scan_spec: Fly,
    seq_table_info: SeqTableInfo,
    motor: Motor,
    panda: HDFPanda,
    restore: bool = False,
) -> MsgGenerator:
    if restore:
        yield from plan_restore_settings(panda=panda, name="seq_table")

    pmac = turbo_slit_pmac()

    yield from ensure_connected(pmac, motor, panda)

    yield from setup_trajectory_scan_pvs()

    # Defining the flyers and components of the scan
    panda_seq = StandardFlyer(StaticSeqTableTriggerLogic(panda.seq[1]))

    pmac_trajectory = PmacTrajectoryTriggerLogic(pmac)
    pmac_trajectory_flyer = StandardFlyer(pmac_trajectory)

    # Prepare Panda file writer trigger info
    panda_hdf_info = TriggerInfo(
        number_of_events=len(
            seq_table_info.sequence_table
        ),  # same as number of rows in sequence table
        trigger=DetectorTrigger.CONSTANT_GATE,
        livetime=scan_spec.duration(),
        deadtime=1e-5,
    )

    @attach_data_session_metadata_decorator()
    @bpp.run_decorator()
    @bpp.stage_decorator([panda, panda_seq])
    def inner_plan():
        yield from bps.declare_stream(panda, name="primary")

        # Prepare pmac with the trajectory
        yield from bps.prepare(pmac_trajectory_flyer, scan_spec, wait=True)
        # prepare sequencer table
        yield from bps.prepare(panda_seq, seq_table_info, wait=True)
        # prepare panda and hdf writer once, at start of scan
        yield from bps.prepare(panda, panda_hdf_info, wait=True)

        # kickoff devices waiting for all of them
        yield from bps.kickoff(panda, wait=True)
        yield from bps.kickoff(panda_seq, wait=True)
        yield from bps.kickoff(pmac_trajectory_flyer, wait=True)

        yield from bps.complete_all(pmac_trajectory_flyer, panda_seq, panda, wait=True)
        yield from bps.collect(
            panda,
            return_payload=True,
            name="primary",
        )

    yield from inner_plan()


def plan_store_settings(panda: HDFPanda, name: str):
    provider = YamlSettingsProvider("./src/spectroscopy_bluesky/i20_1/layouts")
    yield from store_settings(provider, name, panda)


def plan_restore_settings(panda: HDFPanda, name: str):
    print(f"\nrestoring {name} layout\n")
    provider = YamlSettingsProvider("./src/spectroscopy_bluesky/i20_1/layouts")
    settings = yield from retrieve_settings(provider, name, panda)
    yield from apply_panda_settings(settings)
