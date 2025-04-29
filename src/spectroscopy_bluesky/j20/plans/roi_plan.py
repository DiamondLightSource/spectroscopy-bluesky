import bluesky.plan_stubs as bps
import numpy as np
from attr import dataclass
from bluesky.protocols import Movable, Readable
from bluesky.utils import CustomPlanMetadata
from dodal.common.types import MsgGenerator
from ophyd_async.core import TriggerInfo


@dataclass
class QexafsParams:
    quad_multiplier: float
    linear_multiplier: float
    constant: float


@dataclass
class Roi:
    number_of_exposure_points: (
        int  # alternatively provide a step size - that feature can be done later
    )
    start_energy_electron_volts: float
    end_energy_electron_volts: float
    exposure_miliseconds_per_point: float
    qexafs_params: QexafsParams  # in all but the last region this is has 0 for quad and linear components


def get_time(x, p: QexafsParams) -> float:
    return x**2 * p.quad_multiplier + x * p.linear_multiplier + p.constant


def roi_plan(rois: list[Roi], detector: Readable, motor: Movable) -> MsgGenerator:  # type: ignore
    yield from bps.stage_all(*[detector, motor])
    metadata = CustomPlanMetadata()
    yield from bps.open_run(md=metadata)
    sorted_rois = sorted(rois, key=lambda x: x.start_energy_electron_volts)
    for index, region_of_interest in enumerate(sorted_rois):
        print(f"working on roi no: {index}")
        exposure_in_miliseconds_per_each_point_in_this_roi = get_time(
            region_of_interest.start_energy_electron_volts,
            region_of_interest.qexafs_params,
        )
        for s in np.linspace(
            region_of_interest.start_energy_electron_volts,
            region_of_interest.end_energy_electron_volts,
            region_of_interest.number_of_exposure_points,
        ):
            # todo note this motor must be the right one
            yield from bps.mv(motor, s)
            yield from bps.prepare(
                detector,
                TriggerInfo(
                    livetime=exposure_in_miliseconds_per_each_point_in_this_roi,
                    number_of_triggers=1,
                ),
            )
            print("run finished")
    yield from bps.close_run()
    yield from bps.unstage_all(*devices, motor)
