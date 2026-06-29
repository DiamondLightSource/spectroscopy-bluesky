import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from time import sleep, time
from typing import Any

import h5py
from h5py import Dataset, File
from numpy.typing import NDArray


class Datasource(ABC):
    @abstractmethod
    def configure_source(self, source_path: str):
        pass

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def get_num_frames(self) -> int:
        pass

    @abstractmethod
    def set_data_names(self, dataset_names: list[str]):
        pass

    @abstractmethod
    def has_dataset(self, name) -> bool:
        pass

    @abstractmethod
    def read_data(self, start_frame: int, end_frame: int) -> dict[str, NDArray]:
        pass


class HdfDatasource(Datasource):
    def __init__(self, **reader_options: dict[Any, Any]):
        super().__init__()
        self.reader_options: dict[Any, Any] = (
            reader_options or {}
        )  # hdf file reader options
        self.h5_file: File | None = None
        self.dataset_names: list[str] = []
        self.logger = logging.getLogger(self.__class__.__name__)
        self.file_path: str = ""

    def configure_source(self, source_path: str):
        self.file_path = source_path

    def connect(self):
        if self.h5_file is not None:
            self.logger.info(
                f"Closing existing connection to file : {self.h5_file.filename}"
            )
            self.close()
        self.logger.info(f"Connecting to hdf file : {self.file_path}")

        self.h5_file = h5py.File(
            self.file_path, libver="latest", swmr=True, **self.reader_options
        )

        self.h5_datasets: dict[str, Dataset] = {}
        self._setup_datasets()

    def set_data_names(self, dataset_names: list[str]):
        self.dataset_names = dataset_names

    def is_connected(self) -> bool:
        return self.h5_file is not None

    def _check_connected(self):
        if not self.is_connected():
            raise Exception("Cannot get number of frames - not connected to any file")

    def close(self):
        if self.h5_file is not None:
            self.logger.info(
                f"Closing read connection to hdf file {self.h5_file.filename}"
            )
            self.h5_file.close()
            self.h5_file = None
            self.h5_datasets = {}

    def get_num_frames(self) -> int:
        self._check_connected()
        lengths = []
        for dataset in self.h5_datasets.values():
            dataset.refresh()
            lengths.append(dataset.shape[0])
        return min(lengths)

    def has_dataset(self, name):
        return self.h5_file is not None and name in self.h5_file.keys()

    def _setup_datasets(self):
        self._check_connected()
        assert self.h5_file is not None
        for name in self.dataset_names:
            if name not in self.h5_file.keys():
                raise ValueError(
                    f"Could not find dataset called {name} in hdf file {self.file_path}"
                )
            if name not in self.h5_datasets:
                self.h5_datasets[name] = Dataset(self.h5_file[name])

    def read_data(self, start_frame: int, end_frame: int) -> dict[str, NDArray]:
        self._check_connected()

        if len(self.dataset_names) == 0:
            raise ValueError(
                "Cannot read data - names of datasets to be read "
                "have not been set using 'set_data_names'"
            )

        self._setup_datasets()

        data = {}
        for name in self.dataset_names:
            dset = self.h5_datasets[name]
            dset.refresh()
            data[name] = dset[start_frame : end_frame + 1]

        return data


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
        self.h5_file = h5py.File(
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
        if self.h5_datasets is None:
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
    FINISHED_FORCED = 3
    FINISHED_DATA_TIMEOUT = 4
    NOT_SET = 5
    STOPPING = 6


class Processor:
    def __init__(
        self,
        data_source: Datasource,
        processing_config: list[ProcessorFunctionOutput],
        data_writer: HdfDataWriter,
        no_new_data_timeout: float = 5,
        process_loop_sleep_secs: float = 1.0,
    ):
        self.data_source = data_source
        self.processing_config = processing_config
        self.data_writer = data_writer
        self.no_new_data_timeout = no_new_data_timeout
        self.process_loop_sleep_secs = process_loop_sleep_secs

        self.last_frame_read: int = 0
        self.logger = logging.getLogger(self.__class__.__name__)
        self.end_data_loop: bool = False
        self.state = ProcessorState.NOT_STARTED

    def start_processing(self):
        try:
            self.run_processing_loop()
        finally:
            self.logger.info(
                f"Tidying up at end of processing loop - loop state = {self.state}"
            )
            self.data_writer.close()
            self.data_source.close()

    def run_processing_loop(self):

        self.state = ProcessorState.PREPARING

        self.end_data_loop = False

        # make set with names of all the data we need to read
        self.all_data_names = set()
        for config in self.processing_config:
            self.all_data_names.update(config.data_names)
        self.data_source.set_data_names(list(self.all_data_names))

        self.data_source.connect()
        self.check_data_available()

        last_update_time = time()
        self.state = ProcessorState.RUNNING
        while True:
            if self.end_data_loop:
                self.logger.info("Data process loop exited early")
                self.state = ProcessorState.FINISHED_FORCED
                break

            new_processed_data = self.get_processed_data()

            if len(new_processed_data) > 0:
                self.logger.info(f"Processed data : {new_processed_data}")
                self.data_writer.add_data(new_processed_data)
                last_update_time = time()

            if (time() - last_update_time) > self.no_new_data_timeout:
                self.logger.info(
                    f"No new data after {self.no_new_data_timeout} secs "
                    " - exiting readout loop"
                )
                self.state = ProcessorState.FINISHED_DATA_TIMEOUT
                break

            sleep(self.process_loop_sleep_secs)

    def get_state(self) -> ProcessorState:
        return self.state

    def get_processed_data(self) -> dict[str, NDArray]:
        latest_data = self.read_new_frames()

        if len(latest_data) == 0:
            return {}

        print(f"Latest data read    : {latest_data}")
        print(f"Processing data from : {self.processing_config}")
        return self.process_data(latest_data)

    def check_data_available(self):
        missing_data_names = [
            name
            for name in self.all_data_names
            if not self.data_source.has_dataset(name)
        ]
        if len(missing_data_names) > 0:
            raise ValueError(f"Datasets {missing_data_names} not found in data source")

    def read_new_frames(self) -> dict[str, NDArray]:
        current_latest_frame = self.data_source.get_num_frames()
        self.logger.info(
            f"Frames available : {current_latest_frame}, "
            f"last frame added : {self.last_frame_read}"
        )
        if current_latest_frame > self.last_frame_read:
            new_data = self.data_source.read_data(
                self.last_frame_read, current_latest_frame
            )
            self.last_frame_read = current_latest_frame
            return new_data
        return {}

    def get_frame_number(self):
        return self.last_frame_read

    def process_data(self, all_data: dict[str, NDArray]) -> dict[str, NDArray]:
        processed_data: dict[str, NDArray] = {}
        for config in self.processing_config:
            # Create list of NDArrays to be used by processing function
            data = [all_data[name] for name in config.data_names]

            # run the processing function, pass the NDArrays as args.
            processed_data[config.output_path] = config.function(*data)
        return processed_data
