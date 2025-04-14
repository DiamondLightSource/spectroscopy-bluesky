import math

si_d_spacing = 5.4310205


def bragg_to_energy(bragg_angle: float) -> float:
    return si_d_spacing * 2 * math.sin(bragg_angle * math.pi / 180.0)
