import asyncio

from ophyd_async.core import StandardReadable
from ophyd_async.epics.signal import epics_signal_r


class ReadableWithDelay(StandardReadable):

    def __init__(
        self,
        pv_name: str,
        name: str = "",
    ):
        with self.add_children_as_readables():
            self.signal = epics_signal_r(float, pv_name)
        self.delay_before_readout = 0.0
        super().__init__(name=name)

    async def read(self) :
        if self.delay_before_readout > 0 :
            await asyncio.sleep(self.delay_before_readout)
        return await super().read()