import numpy as np
import numpy.typing as npt
from bluesky.utils import MsgGenerator
from dodal.common.coordination import inject
from ophyd_async.epics.motor import Motor
from ophyd_async.fastcs.panda import HDFPanda, SeqTableInfo
from pydantic.dataclasses import dataclass
from scanspec.specs import (
    Axis,
    Dimension,
    Field,
    Fly,
    Line,
    Spec,
    StrictConfig,
    _dimensions_from_indexes,
)

from spectroscopy_bluesky.common.quantity_conversion import (
    energy_to_bragg_angle,
    si_311_lattice_spacing,
)
from spectroscopy_bluesky.common.xas_scans import (
    XasScanParameters,
    XasScanPointGenerator,
)

from .direct_turbo_slit_movement import create_seqtable, seq_table_scan


@dataclass(config=StrictConfig)
class LinePoints(Spec[Axis]):
    """Frames spaced according to positions given in 'points' NDArray.

    .. example_spec::

        from scanspec.specs import Fly, Line

        spec = Fly(Line("x", 1, 2, 5))
    """

    axis: Axis = Field(description="An identifier for what to move")
    points: npt.NDArray = Field(description="Midpoint of the points on the line")

    def axes(self) -> list[Axis]:  # noqa: D102
        return [self.axis]

    def _line_from_indexes(
        self, indexes: npt.NDArray[np.float64]
    ) -> dict[Axis, npt.NDArray[np.float64]]:
        # interpolate points array accordining to indixes :
        # index=0 -> point 0, index=1 -> point 1,
        # index=0.5 = midpoint bwteen point 0 and 1 etc...
        new_points = np.interp(indexes, np.arange(0, len(self.points), 1), self.points)
        return {self.axis: new_points}

    def calculate(  # noqa: D102
        self, bounds: bool = False, nested: bool = False
    ) -> list[Dimension[Axis]]:
        return _dimensions_from_indexes(
            self._line_from_indexes, self.axes(), len(self.points) - 1, bounds
        )


"""
Generate a series of points between 'startpos' and 'endpos'
spaced according to cosine curve :

point[i] = start_pos + 0.5*(1-cos(theta[i]))*(end_pos-start_pos)
theta[i] = pi * i/num_points

"""


def generate_cosine_curve(startpos, endpos, num_points):
    step = np.pi / num_points
    x = np.arange(0, np.pi + step, step)
    return startpos + (endpos - startpos) * (1 - np.cos(x)) * 0.5


def seq_table_element_edge(
    element_name: str,
    edge_name: str,
    duration: float,
    num_readouts: int,
    num_traj_points: int = 20,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
) -> MsgGenerator:
    # Gnerate Xas energy grid for given element and edge
    params = XasScanParameters(element_name, edge_name)
    params.set_from_element_edge()
    params.set_abc_from_gaf()
    params.adjust_a_energy()

    gen = XasScanPointGenerator(params)
    energy_times = gen.calculate_energy_time_grid()
    energy_vals = energy_times[:, 0]

    # Convert energy to Bragg angle
    angles = energy_to_bragg_angle(si_311_lattice_spacing, energy_vals)

    # Create sequence table settings
    table = create_seqtable(angles, time1=1, outa1=True, time2=1, outa2=False)

    seq_table_info = SeqTableInfo(sequence_table=table, repeats=1, prescale_as_us=1)

    # Linear trajectory
    spec = Fly(duration @ (Line(motor, angles[0], angles[-1], num_traj_points)))

    yield from seq_table_scan(spec, seq_table_info, motor=motor, panda=panda)


def nonlinear_trajectory(
    start: float,
    stop: float,
    num_readouts: int,
    duration: float,
    num_trajectory_points: int = 20,
    motor: Motor = inject("turbo_slit_x"),  # noqa: B008
    panda: HDFPanda = inject("panda"),  # noqa: B008
) -> MsgGenerator:
    positions = np.arange(start, stop, (stop - start) / num_readouts)
    table = create_seqtable(positions, time1=1, outa1=True, time2=1, outa2=False)
    seq_table_info = SeqTableInfo(sequence_table=table, repeats=1, prescale_as_us=1)

    trajectory_points = generate_cosine_curve(
        positions[0], positions[-1], num_trajectory_points
    )
    spec = Fly(duration @ (LinePoints(motor, trajectory_points)))

    yield from seq_table_scan(spec, seq_table_info, motor=motor, panda=panda)
