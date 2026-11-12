import asyncio
import logging
import time as time
from contextlib import suppress

import numpy as np
from ophyd_async.core import (
    DetectorAcquireLogic,
    DetectorDataLogic,
    DetectorTriggerLogic,
    PathProvider,
    StandardDetector,
    StreamableDataProvider,
    StreamResourceDataProvider,
    StreamResourceInfo,
    TriggerInfo,
    soft_signal_r_and_setter,
)

from spectroscopy_bluesky.common.processing_service import (
    ProcessingClient,
    ProcessorOutput,
    ProcessorSetup,
)

LOGGER = logging.getLogger(__name__)


class ProcessingRunner:
    def __init__(self, client: ProcessingClient):
        self.client = client
        self.config: ProcessorSetup | None = None
        self.task_id = ""
        self.task: asyncio.Task | None = None
        self.frame_update_interval_secs = 1.0
        self.frames_written, self._update_frames_written = soft_signal_r_and_setter(int)
        self._update_frames_written(0)
        self.processing_finished = False
        self.timeout = 10.0
        self.expected_num_frames: int | None = None
        self.logger = logging.getLogger(type(self).__name__)

    def set_processing_config(self, config: ProcessorSetup):
        self.config = config

    async def start_processing(self, expected_num_frames=None):
        if self.config is None:
            raise Exception(
                "Cannot start processing - no processing configuration has been set!"
            )

        self.expected_num_frames = expected_num_frames
        self.logger.info(f"start_processing called : config = {self.config}")
        # start the processing running on the service
        self.task_id = self.client.start_processor(self.config)
        self.logger.info(f"Task id : {self.task_id}")
        # Start a background process to update number of wrtiten frames signal
        self.task = asyncio.create_task(self._update_num_frames())

    async def _update_num_frames(self):
        self.stop_task = False
        self.processing_finished = False
        state = ""

        while "FINISHED" not in state and not self.stop_task:
            status_dict = self.client.get_task_status(self.task_id)
            self.logger.info(f"Task status : {status_dict}")
            state = status_dict["state"]
            num_frames = int(status_dict["num_frames"])
            self._update_frames_written(num_frames)
            if (
                self.expected_num_frames is not None
                and num_frames >= self.expected_num_frames
            ):
                self.stop_task = True
                self.logger.info("Reached expected number of frames")
            else:
                await asyncio.sleep(self.frame_update_interval_secs)
        self.logger.info("Processing loop finished")
        self.processing_finished = True

    async def stop_processing(self):
        self.logger.info(f"stop_processing called : task id = {self.task_id}")
        if self.task is None or self.task_id == "":
            self.logger.info("No task currently running")
            return
        if not self.processing_finished:
            end_time = time.time() + self.timeout
            while not self.processing_finished and time.time() < end_time:
                self.logger.info("Waiting for processing to finish")
                await asyncio.sleep(0.2)
        if self.processing_finished:
            self.logger.info("Processing finished")
            return

        self.logger.warning(f"Processing not finished after f{self.timeout} secs!")
        self.client.stop_task(self.task_id)
        # Stop the background task and wait for it to finish
        if self.task:
            self.stop_task = True
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
                self.task = None


class TriggerLogic(DetectorTriggerLogic):
    def __init__(self, processing_runner: ProcessingRunner):
        self.processing_runner = processing_runner

    async def prepare_internal(self, num: int, livetime: float, deadtime: float):
        # await self.processing_runner.start_processing(num)
        pass

    async def default_trigger_info(self):
        return TriggerInfo()


class AcquireLogic(DetectorAcquireLogic):
    def __init__(self, processing_runner: ProcessingRunner):
        self.processing_runner = processing_runner

    async def start_acquiring(self):
        pass
        # LOGGER.info("AcquireLogic : start_acquiring called")
        # await self.client_helper.start_processing()

    async def wait_for_idle(self):
        pass  # does this method need to do anything (it doesn't in PandaAcquireLogic)

    async def ensure_stopped(self):
        LOGGER.info("AcquireLogic : ensure_stopped called")
        await self.processing_runner.stop_processing()


class DataLogic(DetectorDataLogic):
    def __init__(
        self,
        processing_runner: ProcessingRunner,
        path_provider: PathProvider | None = None,
    ):
        self.processing_runner = processing_runner
        self.path_provider = path_provider

    # datakey_name is name of the device?
    async def prepare_unbounded(self, datakey_name: str) -> StreamableDataProvider:

        LOGGER.info(f"prepare_unbounded called. datakey_name = {datakey_name}")

        # replace input and output paths using path provider
        if self.path_provider is not None:
            output_path_info = self.path_provider(datakey_name)
            write_path = (
                f"{output_path_info.directory_path}/{output_path_info.filename}.h5"
            )
            self.processing_runner.config.output_file = write_path

            # input from panda1 hdf file
            if self.processing_runner.config.input_files is None:
                input_path_info = self.path_provider("panda1")
                input_path = (
                    f"{input_path_info.directory_path}/{input_path_info.filename}.h5"
                )
                self.processing_runner.config.input_files = [input_path]

        LOGGER.info(
            f"Hdf input file paths : {self.processing_runner.config.input_files}"
        )
        LOGGER.info(
            f"Hdf output file path : {self.processing_runner.config.output_file}"
        )

        await self.processing_runner.start_processing()

        # list of dataset paths in processed hdf file
        output_paths = [
            output.output_path
            for output in self.processing_runner.config.processor_outputs
        ]
        write_path = self.processing_runner.config.output_file

        # mare stream resource objects
        resources = [
            StreamResourceInfo(
                data_key=dataset_name,
                shape=(),
                dtype_numpy=np.dtype(np.float64).str,
                # TODO: make chunk size math actual value used!
                chunk_shape=(1024,),
                parameters={"dataset": f"/{dataset_name}"},
            )
            for dataset_name in output_paths
        ]

        LOGGER.info(f"Stream resource info : {resources}")

        return StreamResourceDataProvider(
            uri=write_path,
            resources=resources,
            mimetype="application/x-hdf5",
            collections_written_signal=self.processing_runner.frames_written,
        )


class DataProcessingDetector(StandardDetector):
    def __init__(
        self,
        processing_service_url: str,
        path_provider: PathProvider | None = None,
        name: str = "",
    ) -> None:
        self.processing_client = ProcessingClient(processing_service_url)
        self.processing_runner = ProcessingRunner(self.processing_client)

        self.add_detector_logics(
            TriggerLogic(self.processing_runner),
            AcquireLogic(self.processing_runner),
            DataLogic(self.processing_runner, path_provider=path_provider),
        )
        super().__init__(name=name)

    def set_processing_config(self, config: ProcessorSetup):
        self.processing_runner.set_processing_config(config)


def create_test_processing():
    # dir_path = path_provider("panda1").directory_path
    dir_path = "/dls/p51/data/2026/cm44254-1"
    # def generate_hdf_path(name):
    #     path_info = path_provider(name)
    #     return path_info.directory_path / f"{path_info.filename}.h5"

    # Set the names of the input hdf file :
    # source_path = str(generate_hdf_path("panda1"))
    # data_name = "inenc-1-val_dataset"

    # URL of socket
    source_path = "bl51p-ts-panda-02"
    data_name = "INENC1.VAL.Min"

    output_file_path = f"{dir_path}/processing_detector.h5"

    setup = ProcessorSetup(
        # input_files=[str(socket)],
        input_files=[source_path],
        output_file=str(output_file_path),
        processor_outputs=[
            ProcessorOutput(
                output_path="encoder_readback",
                function_name="value",
                data_names=[data_name],
            )
        ],
    )
    return setup


def create_processing_detector(setup: ProcessorSetup, path_provider: PathProvider):
    processing_detector = DataProcessingDetector(
        setup,
        "https://p51-processing-service.diamond.ac.uk/",
        name="processing_detector",
        path_provider=path_provider,
    )
    return processing_detector
