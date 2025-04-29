import bluesky.plan_stubs as bps
import numpy as np
from attr import dataclass
from bluesky.protocols import Movable, Readable
from bluesky.utils import CustomPlanMetadata
from dodal.common.types import MsgGenerator
from ophyd_async.core import TriggerInfo


@dataclass
class ExposureScalingParams:
    quad_multiplier: float
    linear_multiplier: float
    constant: float


# todo need to make it possible to vary the step size


@dataclass
class Roi:
    number_of_exposure_points: (
        int  # alternatively provide a step size - that feature can be done later
    )
    start_energy_electron_volts: float
    end_energy_electron_volts: float
    exposure_seconds_per_point: float
    qexafs_params: ExposureScalingParams  # in all but the last region this is has 0 for quad and linear components


def get_time(x, p: ExposureScalingParams) -> float:
    return x**2 * p.quad_multiplier + x * p.linear_multiplier + p.constant


# detector is ion chambers (i0, it), maybe also xspres3/4, motor is always the monochromator
def roi_plan(rois: list[Roi], detector: Readable, motor: Movable) -> MsgGenerator:  # type: ignore
    yield from bps.stage_all(*[detector, motor])
    metadata = CustomPlanMetadata()
    yield from bps.open_run(md=metadata)
    sorted_rois = sorted(rois, key=lambda x: x.start_energy_electron_volts)
    for index, region_of_interest in enumerate(sorted_rois):
        print(f"working on roi no: {index}")
        for s in np.linspace(
            region_of_interest.start_energy_electron_volts,
            region_of_interest.end_energy_electron_volts,
            region_of_interest.number_of_exposure_points,
        ):
            exposure_for_this_step = get_time(
                s,
                region_of_interest.qexafs_params,
            )
            # todo note this motor must be the right one
            yield from bps.mv(motor, s)
            yield from bps.prepare(
                detector,
                TriggerInfo(
                    livetime=exposure_for_this_step,
                    number_of_triggers=1,
                ),
            )
            print("run finished")
    yield from bps.close_run()
    yield from bps.unstage_all(*devices, motor)
