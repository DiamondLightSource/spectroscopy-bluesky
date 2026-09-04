import logging
import traceback
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from time import sleep, time
from typing import Any

from h5py import Dataset, File
from numpy.typing import NDArray

from .data_sources import Datasource


class HdfDataWriter:
    def __init__(self, file_path: str, **writer_options):
        self.file_path = file_path
        self.writer_options = writer_options
        self.h5_file: File | None = None
        self.h5_datasets: dict[str, Dataset] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def set_file_path(self, file_path: str):
        self.file_path = file_path

    def _open_file(self):
        self.close()
        self.logger.info(f"Opening hdf file {self.file_path}")
        self.h5_file = File(
            self.file_path, mode="w", libver="latest", **self.writer_options
        )

    def _setup_datasets(self, data: dict[str, NDArray]):
        if self.h5_file is None:
            raise Exception("Cannot setup datasets - no file has been opened!")

        self.h5_datasets = {}
        for name, values in data.items():
            if len(values.shape) == 1:
                shape = (0,)
            else:
                shape = tuple([0] * len(values.shape))

            # set unlimited size for outermost dimension :
            maxshape = list(values.shape)
            maxshape[0] = None

            self.logger.info(
                f"Dataset '{name}' : shape = {shape}, maxshape = {maxshape}"
            )

            self.h5_datasets[name] = self.h5_file.create_dataset(
                name, shape=shape, maxshape=maxshape, dtype="f4"
            )

        # enable swmr mode *after* creating the datasets
        self.h5_file.swmr_mode = True

    def add_data(self, new_data: dict[str, NDArray]):
        if len(self.h5_datasets) == 0:
            self._open_file()
            self._setup_datasets(new_data)

        # To keep pyright happy
        assert self.h5_file is not None

        self.logger.info(f"Updating data in {self.file_path}")

        if len(self.h5_datasets) == 0:
            raise Exception("Cannot add data - no datasets have been setup!")

        for name, data in new_data.items():
            num_new_frames = data.shape[0]
            current_shape = self.h5_datasets[name].shape

            new_shape = list(data.shape)
            new_shape[0] = current_shape[0] + num_new_frames

            self.logger.info(
                f"Data : {name}, current shape : {current_shape}, "
                f"new shape : {new_shape}"
            )
            # get h5 dataset, resize it, append the data
            dataset = self.h5_datasets[name]
            dataset.resize(new_shape)
            self.h5_datasets[name][current_shape[0] : new_shape[0]] = data

        self.h5_file.flush()

    def close(self):
        if self.h5_file is not None:
            self.logger.info(f"Closing processed hdf file {self.h5_file.filename}")
            self.h5_file.flush()
            self.h5_file.close()
        self.h5_datasets = {}


@dataclass
class ProcessorFunctionOutput:
    output_path: str
    function: Any  # function reference or lambda function
    data_names: list[str]


class ProcessorState(Enum):
    NOT_STARTED = 0
    PREPARING = 1
    RUNNING = 2
    FINISHED_STOPPED = 3
    FINISHED_TIMEOUT = 4
    FINISHED_ERROR = 5
    NOT_SET = 6
    STOPPING = 7


class Processor:
    def __init__(
        self,
        data_sources: list[Datasource],
        processing_config: list[ProcessorFunctionOutput],
        data_writer: HdfDataWriter,
        no_new_data_timeout: float = 5,
        process_loop_sleep_secs: float = 1.0,
    ):
        self.all_data_sources = data_sources
        self.processing_config = processing_config
        self.data_writer = data_writer
        self.no_new_data_timeout = no_new_data_timeout
        self.process_loop_sleep_secs = process_loop_sleep_secs

        self.last_frame_read: int = 0
        self.logger = logging.getLogger(self.__class__.__name__)
        self.end_data_loop: bool = False
        self.state = ProcessorState.NOT_STARTED
        self.error_message: str | None = None
        self.error_traceback: list[str] | None = None

    def start_processing(self):
        try:
            self.run_processing_loop()
        finally:
            if self.state not in [
                ProcessorState.FINISHED_STOPPED,
                ProcessorState.FINISHED_TIMEOUT,
            ]:
                self.state = ProcessorState.FINISHED_ERROR
                self.error_traceback = traceback.format_exc().splitlines()
                self.error_message = self.error_traceback[-1]

            self.logger.info(
                f"Tidying up at end of processing loop - loop state = {self.state}"
            )

            self.data_writer.close()
            for data_source in self.all_data_sources:
                data_source.close()

    def _active_data_sources(self) -> list[Datasource]:
        return list(self.datasource_datanames.keys())

    def run_processing_loop(self):

        self.state = ProcessorState.PREPARING

        self.end_data_loop = False

        # connect all sources to their hdf files
        for source in self.all_data_sources:
            source.connect()

        # map with data to be read from each source
        self.datasource_datanames: dict[Datasource, set[str]] = defaultdict(set)

        for config in self.processing_config:
            for data_name in config.data_names:
                # see which datasource has the data
                source = [s for s in self.all_data_sources if s.has_dataset(data_name)]

                # there must be exactly 1 source for the data
                if len(source) == 0:
                    raise ValueError(
                        f"Could not find data called '{data_name}' in "
                        "any of the data sources!"
                    )
                if len(source) > 1:
                    raise ValueError(
                        f"Expected only 1 source for '{data_name}' data "
                        f"but found {len(source)} ({source})!"
                    )
                self.datasource_datanames[source[0]].add(data_name)

        for source, data_names in self.datasource_datanames.items():
            source.set_data_names(list(data_names))

        last_update_time = time()
        self.state = ProcessorState.RUNNING
        while True:
            if self.end_data_loop:
                self.logger.info("Data process loop exited early")
                self.state = ProcessorState.FINISHED_STOPPED
                break

            new_processed_data = self.get_processed_data()

            if len(new_processed_data) > 0:
                self.logger.debug(f"Processed data : {new_processed_data}")
                self.data_writer.add_data(new_processed_data)
                last_update_time = time()

            if (time() - last_update_time) > self.no_new_data_timeout:
                self.logger.info(
                    f"No new data after {self.no_new_data_timeout} secs "
                    " - exiting readout loop"
                )
                self.state = ProcessorState.FINISHED_TIMEOUT
                break

            sleep(self.process_loop_sleep_secs)

    def get_state(self) -> ProcessorState:
        return self.state

    def get_processed_data(self) -> dict[str, NDArray]:
        all_data = self.read_new_frames()

        if len(all_data) == 0:
            return {}

        return self.process_data(all_data)

    def get_num_frames(self) -> int:
        frame_numbers = [
            source.get_num_frames() for source in self._active_data_sources()
        ]
        self.logger.debug(f"Frames available : {frame_numbers}")
        return min(frame_numbers)

    def read_new_frames(self) -> dict[str, NDArray]:
        current_latest_frame = self.get_num_frames()
        self.logger.info(
            f"Frames available : {current_latest_frame}, "
            f"Last frame added : {self.last_frame_read}"
        )
        all_data: dict[str, NDArray] = {}
        if current_latest_frame > self.last_frame_read:
            # get data from all data sources
            for source in self._active_data_sources():
                all_data.update(
                    source.read_data(self.last_frame_read, current_latest_frame)
                )
            for name, data in all_data.items():
                self.logger.info(f"{name} - {data.shape}")
            self.last_frame_read = current_latest_frame
        return all_data

    def get_frame_number(self):
        return self.last_frame_read

    def process_data(self, all_data: dict[str, NDArray]) -> dict[str, NDArray]:
        processed_data: dict[str, NDArray] = {}
        for config in self.processing_config:
            # Create list of NDArrays to be used by processing function
            self.logger.info(f"Processing data for {config.output_path}")

            if (
                config.output_path is None
                or config.output_path == ""
                or len(config.data_names) == 0
            ):
                # copy everything
                processed_data.update(all_data)
            else:
                # extract required NDArrays
                data = [all_data[name] for name in config.data_names]
                print(f"Data for {config.output_path} : {data}")
                # run the processing function, pass the NDArrays as args.
                processed_data[config.output_path] = config.function(*data)

        return processed_data
