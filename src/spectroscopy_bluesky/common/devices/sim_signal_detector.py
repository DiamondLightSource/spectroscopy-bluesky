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


class FunctionPatternGenerator:
    """
        Class to be used with SimSignalDetector. 
        Each call to `generate_point` evaluates a user specified function.
    """
    def __init__(self):
        self._x = 0.0

        # function that takes float and optional parameters and returns a value
        self.user_function = math.sin

        # parameters to be passed to user_function 
        self.function_params: list[float] = []

        # set the function to be used to generate random numbers [0,1)
        self.rnd_generator = random.random
        random.seed(1)

        # Extra noise to be added to generated values (absolute value).
        self.noise: float = 0.0

    def set_x(self, x: float):
        self._x = x

    def generate_value(self, x_value: float):
        """Generate value from `self.user_function`. Passes x_value
        as first parameter, followed by each parameter in
        `self.function_params` list.

        i.e. user_function(x_value, *function_params)

        Args:
            x_value (float): _description_

        Returns:
            float: result of evaluating `self.user_function`
        """
        return self.user_function(x_value, *self.function_params)

    def generate_point(self, x_value=None) -> float:
        if x_value is None :
            x_value = self._x
        val = self.generate_value(x_value)
        if self.noise > 0 :
            val += self.rnd_generator()*self.noise
        return val


class SimSignalDetector(StandardReadable):
    """ Detector with several channels, single value per channel.
    Value for each channel is provided by 'generator' function"""

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