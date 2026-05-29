import math


class XesCalculator:
    R: float
    """ Rowland circle radius (mm) """

    detector_axis_angle: float
    """ Angle of detector translation axes wrt to spectrometer axes (degrees)"""

    horizontal_offset: float
    """ Horizonal offset between adjacent analysers (mm) """

    def __init__(self, R: float, offset: float = 137.0, detector_axis_angle: float = 0):
        self.R = R
        self.horizontal_offset = offset
        self.detector_axis_angle = detector_axis_angle

    def _rotate(self, angle_rad: float, x: float, y: float) -> list[float]:
        """Transform x, y coordinate by applying a rotation.
        Args:
            angle_rad (float): rotation angle (radians)
            x (float): x position
            y (float): y position

        Returns:
            list[float]: _description_
        """
        return [
            x * math.cos(angle_rad) + y * math.sin(angle_rad),
            -x * math.sin(angle_rad) + y * math.cos(angle_rad),
        ]

    def _get_dx(self, bragg_rad: float) -> float:
        return self.R * math.sin(bragg_rad) * (1 + math.cos(2.0 * bragg_rad))

    def _get_dy(self, bragg_rad: float) -> float:
        return self.R * math.sin(bragg_rad) * math.sin(2.0 * bragg_rad)

    def _get_p(self, bragg_rad: float, offset: float):
        sinTheta = math.sin(bragg_rad)
        return math.sqrt((self.R * sinTheta * sinTheta) ** 2 - offset**2)

    def calculate_analyser_position(
        self, bragg_angle_deg: float, analyser_index: int = 0
    ) -> list[float]:
        """_summary_

        Args:
            R (float): Rowland circle radius(mm)
            bragg_angle_deg (float): Bragg angle (degrees)
            analyser_index (int): index of analyser (0 for central, +1, -1
            for analysers either side of centre etc)

        Returns:
            list[float]: x, y, yaw, pitch values for analyser stage (angles in degrees)
        """

        offset = analyser_index * self.horizontal_offset

        bragg_rad = math.radians(bragg_angle_deg)
        p = self._get_p(bragg_rad, offset)
        sinTheta = math.sin(bragg_rad)
        cosTheta = math.cos(bragg_rad)
        ax = self.R * sinTheta * cosTheta * cosTheta + p * sinTheta
        ay = self.R * cosTheta * sinTheta * sinTheta - p * cosTheta

        pitch = 0.5 * math.pi - math.atan(
            math.sqrt(offset * offset + p * p * sinTheta * sinTheta) / (p * cosTheta)
        )
        yaw = math.atan(offset / (p * sinTheta))
        return [ax, ay, math.degrees(yaw), math.degrees(pitch)]

    def calculate_detector_position(self, bragg_angle_deg: float) -> list[float]:
        """Calculate detector position (in rotated detector axis coordinate system,
        according to `detector_axis_angle`.

        Args:
            bragg_angle_deg (float): Bragg angle (degrees)

        Returns:
            list[float]: x, y, pitch values for detector stage (angle in degrees)
        """
        bragg_rad = math.radians(bragg_angle_deg)
        detX = self._get_dx(bragg_rad)
        detY = self._get_dy(bragg_rad)
        theta = float(90 - bragg_angle_deg)

        # transform x and y to rotated detector frame of reference :
        rotVals = self._rotate(math.radians(self.detector_axis_angle), detX, detY)
        return [rotVals[0], rotVals[1], 2 * theta]

    def calculate_bragg_angle(self, detector_rotation_deg: float):
        return 90.0 - abs(detector_rotation_deg) * 0.5
