import asyncio
import math
from dataclasses import dataclass

import numpy as np
from bluesky.protocols import Movable
from ophyd_async.core import (
    Array1D,
    AsyncStatus,
    Device,
    StandardReadable,
    soft_signal_r_and_setter,
)
from ophyd_async.core import StandardReadableFormat as Format
from ophyd_async.epics.motor import Motor

from spectroscopy_bluesky.common.devices.spectrometer import XesCalculator
from spectroscopy_bluesky.common.quantity_conversion import (
    crystal_spacing,
    energy_to_bragg_angle,
    lattice_parameter_si,
)


class EnergyConvertor:
    miller_indices: list[int]
    lattice_parameter: float

    def __init__(self, miller_indices=None, lattice_parameter=lattice_parameter_si):
        self.miller_indices = (
            miller_indices if miller_indices is not None else [1, 1, 1]
        )
        self.lattice_parameter = lattice_parameter

    def convert_to_bragg(self, energy_ev):
        spacing = crystal_spacing(self.lattice_parameter, self.miller_indices)
        return energy_to_bragg_angle(spacing, energy_ev)


class SpectrometerComponentDevice(Device):
    def __init__(self, motor_list: list[Motor], name: str = ""):
        self.motor_list = motor_list
        super().__init__(name=name)

    async def move_to(self, positions: list[float]):
        """Move each motor to given position

        Args:
            positions (list[float]): position for each motor
        """
        coros = [
            motor.set(position)
            for motor, position in zip(self.motor_list, positions, strict=True)
        ]
        await asyncio.gather(*coros)

    async def check_tolerance(
        self, demand_positions: list[float], tolerances: list[float]
    ) -> bool:
        """Check to see if current motor readback positions are within
        a given tolerance of demand_positions. Return true if tolerance
        is exceeded for any of the motors. i.e. : <br>

        abs(motor_rbv[i] - demand_positions[i]) > tolerances[i]

        Args:
            demand_positions (list[float]): list of positions to compare with
            tolerances (list[float]): tolerance for each motor position

        Returns:
            bool: _description_
        """
        current_positions = await self.get_rbv_positions()
        outside_tolerance = [
            math.fabs(p1 - p2) > tol
            for p1, p2, tol in zip(
                demand_positions, current_positions, tolerances, strict=True
            )
        ]
        return outside_tolerance.count(True) > 0

    async def get_rbv_positions(self) -> list[float]:
        """Return list of motor readback (rbv) values

        Returns:
            list[float]: rbv value for each motor
        """
        coros = [motor.user_readback.get_value() for motor in self.motor_list]
        return await asyncio.gather(*coros)


@dataclass
class AnalyserPosition:
    x: float
    y: float
    yaw: float
    pitch: float

    def get_positions(self) -> list[float]:
        return [self.x, self.y, self.yaw, self.pitch]


@dataclass
class DetectorPosition:
    x: float
    y: float
    pitch: float

    def get_positions(self) -> list[float]:
        return [self.x, self.y, self.pitch]


class DetectorDevice(SpectrometerComponentDevice, Movable[DetectorPosition]):
    def __init__(self, prefix: str, name: str = ""):
        self.x_motor = Motor(prefix + ":X")
        self.y_motor = Motor(prefix + ":Y")
        self.pitch_motor = Motor(prefix + ":PITCH")
        super().__init__([self.x_motor, self.y_motor, self.pitch_motor], name=name)

    @AsyncStatus.wrap
    async def set(self, position: DetectorPosition):
        self.log.info(f"Moving {self.name} to {position}s")
        await self.move_to(position.get_positions())


class AnalyserDevice(SpectrometerComponentDevice, Movable[AnalyserPosition]):
    def __init__(self, prefix: str, index: int, name: str = ""):
        self.x_motor = Motor(prefix + ":X")
        self.y_motor = Motor(prefix + ":Y")
        self.yaw_motor = Motor(prefix + ":YAW")
        self.pitch_motor = Motor(prefix + ":PITCH")
        self.allowed_to_move = True
        self.horizontal_index = index
        super().__init__(
            [self.x_motor, self.y_motor, self.yaw_motor, self.pitch_motor], name=name
        )

    @AsyncStatus.wrap
    async def set(self, position: AnalyserPosition):
        self.log.debug(f"Moving {self.name} to {position}s")
        await self.move_to(position.get_positions())


class XesSpectrometerBragg(StandardReadable, Movable[float]):
    analyser_crystals: list[AnalyserDevice]
    rowland_circle_radius: float
    xes_calculator: XesCalculator
    detector_device: DetectorDevice
    trajectory_step_size: float
    analyser_move_tolerance: list[float]
    detector_move_tolerance: list[float]
    bragg_lower_limit: float
    bragg_upper_limit: float

    def __init__(
        self,
        rowland_circle_radius: float,
        analysers: list[AnalyserDevice],
        detector_device: DetectorDevice,
        name: str = "",
    ):
        self.rowland_circle_radius = rowland_circle_radius
        self.xes_calculator = XesCalculator(rowland_circle_radius)
        self.analyser_crystals = analysers
        self.detector_device = detector_device
        self.trajectory_step_size = 0.02
        self.analyser_move_tolerance = [0, 0, 0, 0]
        self.detector_move_tolerance = [0, 0, 0]
        self.bragg_angle_rbv, self.bragg_angle_setter = soft_signal_r_and_setter(
            float, 90.0, units="deg"
        )
        self.add_readables([self.bragg_angle_rbv], Format.HINTED_UNCACHED_SIGNAL)

        self.bragg_lower_limit = 60.0
        self.bragg_upper_limit = 86.0

        super().__init__(name)

    @AsyncStatus.wrap
    async def set(self, bragg_angle_deg: float):

        # check Bragg angle is within range
        self.log.debug(f"Setting Bragg angle to {bragg_angle_deg}")
        if (
            bragg_angle_deg < self.bragg_lower_limit
            or bragg_angle_deg > self.bragg_upper_limit
            or math.isnan(bragg_angle_deg)
            or math.isinf(bragg_angle_deg)
        ):
            raise ValueError(
                f"Bragg angle {bragg_angle_deg} is not within allowed limits "
                f"{self.bragg_lower_limit} ... {self.bragg_upper_limit}"
            )

        # calculate Bragg angle from angle of detector
        det_rotation = await self.detector_device.pitch_motor.user_readback.get_value()
        current_bragg_angle = self.xes_calculator.calculate_bragg_angle(det_rotation)

        self.log.debug(
            f"Current Bragg angle (from detector angle) : {current_bragg_angle}"
        )

        coros = []

        if abs(bragg_angle_deg - current_bragg_angle) > self.trajectory_step_size:
            # For large change, move detector along trajectory
            coros.append(
                self.move_detector_trajectory(current_bragg_angle, bragg_angle_deg)
            )
        else:
            # For small change move directly to required position
            detpos = self.xes_calculator.calculate_detector_position(bragg_angle_deg)

            currpos = await self.detector_device.get_rbv_positions()
            do_move = await self.detector_device.check_tolerance(
                detpos, self.detector_move_tolerance
            )
            self.log.debug(
                f"Moving {self.detector_device.name} to {detpos}. do move = {do_move}"
                f"Current position : {currpos}"
            )
            if do_move:
                coros.append(self.detector_device.set(DetectorPosition(*detpos)))

        for c in self.analyser_crystals:
            pos = self.xes_calculator.calculate_analyser_position(
                bragg_angle_deg, c.horizontal_index
            )
            do_move = await c.check_tolerance(pos, self.analyser_move_tolerance)

            self.log.debug(f"Moving {c.name} to {pos} :")
            self.log.debug(
                f"Allowed to move = {c.allowed_to_move}, do move = {do_move}"
            )
            if do_move and c.allowed_to_move:
                coros.append(c.set(AnalyserPosition(*pos)))

        # wait for all to finish moving
        self.log.info("Waiting for motor moves to finish")
        await asyncio.gather(*coros)
        self.bragg_angle_setter(bragg_angle_deg)
        self.log.info("Moves finished")

    async def move_detector_trajectory(self, start_bragg: float, end_bragg: float):
        self.log.info(
            f"Moving detector along trajectory between Bragg angles : {start_bragg} "
            f" and {end_bragg} degrees "
        )
        num_steps = abs(end_bragg - start_bragg) / self.trajectory_step_size
        for angle in np.linspace(start_bragg, end_bragg, int(num_steps)):
            detector_pos = self.xes_calculator.calculate_detector_position(angle)
            self.log.debug(
                f"{self.detector_device.name} : {angle:.2f} -> {detector_pos}"
            )
            await self.detector_device.set(DetectorPosition(*detector_pos))


class XesSpectrometerEnergy(StandardReadable, Movable[float]):
    def __init__(
        self,
        spectrometer_bragg: XesSpectrometerBragg,
        crystal_cut: list[int],
        lattice_parameter: float = lattice_parameter_si,
        name: str = "",
    ):
        self.spectrometer_bragg = spectrometer_bragg.set
        self.energy_converter = EnergyConvertor()
        self.energy_converter.miller_indices = crystal_cut
        self.lattice_parameter = lattice_parameter

        with self.add_children_as_readables(Format.HINTED_UNCACHED_SIGNAL):
            self.crystal_cut, self.crystal_cut_setter = soft_signal_r_and_setter(
                Array1D[np.int8], name="crystal_cut"
            )
            self.xes_energy, self.xes_energy_setter = soft_signal_r_and_setter(
                float, name="xes_energy", units="eV"
            )
            self.xes_bragg, self.xes_bragg_setter = soft_signal_r_and_setter(
                float, name="xes_bragg", units="degrees"
            )

        self.set_crystal_cut(crystal_cut)

        super().__init__(name=name)

    def set_crystal_cut(self, crystal_cut: list[int]):
        self.crystal_cut_setter(np.array(crystal_cut, dtype=np.int8))

    @AsyncStatus.wrap
    async def set(self, energy_ev: float):
        crystal_cut = await self.crystal_cut.get_value()
        self.energy_converter.miller_indices = crystal_cut.tolist()
        self.energy_converter.lattice_parameter = self.lattice_parameter
        try:
            bragg_angle = self.energy_converter.convert_to_bragg(energy_ev)
        except Exception as err:
            raise ValueError(
                f"Problem converting energy {energy_ev}eV to Bragg angle"
            ) from err

        if math.isnan(bragg_angle) or math.isinf(bragg_angle):
            raise ValueError(f"Could not convert energy {energy_ev}eV to Bragg angle")

        self.log.info(f"Moving {self.name} to {energy_ev} eV ({bragg_angle} degrees)")

        self.xes_energy_setter(energy_ev)

        self.xes_bragg_setter(bragg_angle)
        await self.spectrometer_bragg(bragg_angle)
