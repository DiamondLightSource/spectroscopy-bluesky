from ophyd_async.core import (
    StandardReadable,
)
from ophyd_async.epics.motor import Motor


class AlignmentStage(StandardReadable):
    """ Collection of motors to control the alignment stage """
    def __init__(self, beamline_prefix: str, name: str = "") -> None:
        with self.add_children_as_readables():
            self.x = Motor(beamline_prefix + "-MO-STAGE-01:X")
            self.y = Motor(beamline_prefix + "-MO-STAGE-01:Y")
            self.slit_x = Motor(beamline_prefix + "-AL-SLITS-04:X")
            self.slit_gap = Motor(beamline_prefix + "-AL-SLITS-04:GAP")
            self.shutter_y = Motor(beamline_prefix + "-EA-SHTR-01:Y")
        super().__init__(name=name)
