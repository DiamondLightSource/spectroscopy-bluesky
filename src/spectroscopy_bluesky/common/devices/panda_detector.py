import asyncio  # noqa: I001
import logging

from bluesky.protocols import Preparable, Triggerable
from ophyd_async.core import (
    AsyncStatus,
    DetectorTrigger,
    DeviceVector,
    SignalR,
    StandardReadable,
    TriggerInfo,
    soft_signal_rw,
    wait_for_value,
)
from ophyd_async.fastcs.panda import HDFPanda, SeqTable, PandaTimeUnits, PandaBitMux

from spectroscopy_bluesky.common.panda_data_socket import DataSocket


class PandaDetector(StandardReadable, Preparable, Triggerable):
    def __init__(
        self, name: str, panda_device: HDFPanda, data_dict: dict[str, str] | None = None
    ) -> None:
        self.panda_device = panda_device
        self.num_channels = 3
        self.chan_data: DeviceVector | None = None
        self.frame_time: int = 1000
        self.dead_time: int = 10
        self.sleep_time: float = 0.0
        self.prescale_units: PandaTimeUnits = PandaTimeUnits.MS
        self.prescale: float = 1
        self.use_hdf_writer = False
        self.data_socket: DataSocket | None = None

        """ Dict specifying data be read from the Panda data stream :
        key = name of signal name in this device, 
        value = name of field in Panda data stream """
        self.socket_data_dict = (
            data_dict  # {"counts1": "COUNTER1.OUT", "adc1": "FMC_IN.VAL1"}
        )

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        with self.add_children_as_readables():
            self.frame_counter = soft_signal_rw(int, initial_value=None, units=None)

        # set custom names for data after __init__ has been called
        self.setup_data_channels()
        super().__init__(name)

    def setup_data_channels(self):
        data_names = self.socket_data_dict.keys()

        with self.add_children_as_readables():
            output_names = [self.name + "-" + name for name in data_names]

            self.chan_data = DeviceVector(
                {
                    i: soft_signal_rw(
                        float,
                        initial_value=0,
                        name=output_name,
                        units=None,
                        precision=10,
                    )
                    for i, output_name in enumerate(output_names)
                }
            )

    async def prepare_panda(self):
        self.logger.info("Prepare panda")
        # make sure pcap and sequence table are stopped first

        self.logger.info("Stopping PCap and SEQ1 table")
        await self.panda_device.pcap.arm.set(False)
        seq_block = self.panda_device.seq[1]

        # Stop the sequence table
        await seq_block.enable.set(PandaBitMux.ZERO)
        await wait_for_value(seq_block.active, False, 10)

        self.prepare_data_socket()

        # apply the prescale settings
        self.logger.info("Setting prescale")
        await seq_block.prescale_units.set(self.prescale_units)
        await seq_block.prescale.set(self.prescale)

        # Each frame is started by trigger from PULSE1 input to BitA
        await seq_block.bita.set("PULSE1.OUT")

        # setup the sequence table
        row_params = SeqTable.row(
            repeats=0,
            trigger="BITA=1",
            time1=self.frame_time,
            outa1=True,
            time2=self.dead_time,
        )
        self.logger.info("Setting up sequence table")
        await seq_block.table.set(row_params)

        if self.use_hdf_writer:
            trigger_info = TriggerInfo()
            trigger_info.number_of_events = 0
            trigger_info.livetime = 1.0
            trigger_info.deadtime = 0.1
            trigger_info.trigger = DetectorTrigger.INTERNAL

            # arm the panda and start the hdf data writer
            await self.panda_device.prepare(trigger_info)

        self.logger.info("Arming PCap")
        await self.panda_device.pcap.arm.set(True)
        await wait_for_value(self.panda_device.pcap.active, True, 10)

        # wait for seq table to become active (also resets 'line repeat' and
        # 'table line' etc back to 1)
        self.logger.info("Enabling SEQ1")
        await seq_block.enable.set(PandaBitMux.ONE)
        await wait_for_value(seq_block.active, True, 10)

    def prepare_data_socket(self):
        self.logger.info("Preparing panda data socket")
        self.data_socket.disconnect()
        self.data_socket.connect()
        self.data_socket.collect_data_in_thread()

    async def stop_panda(self):
        if self.use_hdf_writer:
            await self.panda_device.unstage()
        else:
            await self.panda_device.pcap.arm.set(0)

    @AsyncStatus.wrap
    async def stage(self) -> None:
        self.count = 0
        await self.prepare_panda()

    @AsyncStatus.wrap
    async def unstage(self) -> None:
        self.logger.debug("Unstage called")
        await self.stop_panda()

    @AsyncStatus.wrap
    async def prepare(self, value) -> None:
        self.logger.debug("prepare called", value)
        pass

    def total_num_frames(self) -> SignalR[int]:
        return self.panda_device.seq[1].line_repeat

    @AsyncStatus.wrap
    async def trigger(self) -> None:
        self.frame_counter.set(self.count)

        num_frames_before_trigger = await self.total_num_frames().get_value()

        self.logger.debug("Frame number before trigger : %d", num_frames_before_trigger)

        # Make sure pulse block is enabled
        await self.panda_device.pulse[1].enable.set("ONE")

        # trigger 1 frame on sequence table by using pulse block
        await self.panda_device.pulse[1].trig.set("ZERO")
        await asyncio.sleep(self.sleep_time)
        await self.panda_device.pulse[1].trig.set("ONE")

        # wait for line_repeat to increment
        self.logger.debug("Waiting for frame number to increment")
        await wait_for_value(
            self.total_num_frames(), lambda val: val > num_frames_before_trigger, 10
        )

        self.count += 1

        await self.update_readout_values()

    async def update_readout_values(self):
        """
        Update the chan_dat signals using the latest values from the
        panda data stream
        """

        # Wait for the last frame of data to be available
        num_frames = self.count
        while self.data_socket.get_num_frames() < num_frames:
            await asyncio.sleep(0.1)

        # read latest frame of data
        # frame_data = self.data_socket.get_frame(num_frames - 1)
        frame_values = self.data_socket.get_frame_values(num_frames - 1)

        # extract the data for the named fields in socket_data_dict
        self.logger.debug(
            f"Panda socket data for frame {num_frames - 1} : {frame_values}"
        )
        for index, name in enumerate(self.socket_data_dict.values()):
            col = self.data_socket.data_field_names.index(name)
            dat_val = frame_values[col]
            self.logger.debug(f"{name} {col} = {dat_val}")
            await self.chan_data[index].set(dat_val)

    # @AsyncStatus.wrap
    # async def read(self) -> dict[str, Reading]:
    #     await self.update_readout_values()
    #     return await super().read()

    @AsyncStatus.wrap
    async def kickoff(self) -> None:
        pass

    @AsyncStatus.wrap
    async def complete(self) -> None:
        self.logger.debug("Complete called")
        pass  # await self.panda_device.pcap.arm.set(0)

    def describe_collect(self):
        return super().describe()
        # return {"stream_name": {"test"}}
