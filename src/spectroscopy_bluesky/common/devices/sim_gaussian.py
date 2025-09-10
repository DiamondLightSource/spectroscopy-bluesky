import math
import random
from collections.abc import Callable

from ophyd_async.core import (
    AsyncStatus,
    DeviceVector,
    StandardReadable,
    soft_signal_r_and_setter,
)
from ophyd_async.core import StandardReadableFormat as Format


class GaussianPatternGenerator:

    def __init__(self):
        self._x = 0.0
        self.rnd_generator = random.random
        random.seed(1)
        self.noise: float = 0.0
        self.centre: float = 0
        self.sigma: float = 1.0
        self.height: float = 1.0

    def set_x(self, x: float):
        self._x = x

    def set_fwhm(self, fwhm: float) :
        # fwhm = 2*sqrt(2*ln(2)) * sigma
        self.sigma = fwhm /(2.0*math.sqrt(2*math.log(2)))

    def generate_point(self, x_value=None) -> float:
        if x_value is None :
            x_value = self._x
        val = self.height * math.exp( -((x_value - self.centre)/(2.0*self.sigma))**2 )
        if self.noise > 0 :
            val += self.rnd_generator()*self.noise
        return val


class SimSignalDetector(StandardReadable):
    """ Detector with several channels, single value per channel."""

    def __init__(
        self, generator: Callable[[], float],
        num_channels: int = 1, name: str = "",
        precision = 5
    ) -> None:
        self._generator = generator

        self._value_signals = dict(
            soft_signal_r_and_setter(float, precision=precision) for _ in range(num_channels)
        )
        with self.add_children_as_readables(Format.HINTED_SIGNAL):
            self.channel = DeviceVector(
                {
                    i + 1: value_signal
                    for i, value_signal in enumerate(self._value_signals)
                }
            )
        super().__init__(name=name)

    async def _update_values(self):
        for i, signal in self.channel.items():
            point = self._generator()
            setter = self._value_signals[signal]
            setter(point)

    @AsyncStatus.wrap
    async def trigger(self):
        await self._update_values()