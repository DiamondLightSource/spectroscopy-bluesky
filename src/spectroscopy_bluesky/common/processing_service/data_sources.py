import logging
import socket
import typing
from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import Thread
from time import sleep
from typing import Any

import numpy as np
from h5py import Dataset, File
from numpy.typing import NDArray
from pandablocks.connections import DataConnection, EndData, FrameData, StartData


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


@dataclass
class FrameNumberAndData:
    start_frame: int
    frame_data: FrameData

    def get_frames(self, first_frame: int, last_frame: int) -> NDArray:
        """Return a range of frames from the stored FrameData data object
        from first_frame to last_frame (exclusive)
        Args:
            first_frame (int):
            last_frame (int): use -1 for last available frame

        Returns:
            NDArray: A numpy `Structured Array` -
                as descibed in :func:`~pandablocks.connections.FrameData`
        """
        r = self._range(first_frame, last_frame)
        return self.frame_data.data[r[0] : r[1]]

    def _frame_index_in_data(self, frame_number) -> int:
        if frame_number == -1:
            return self.last_frame()
        return frame_number - self.start_frame

    def _range(self, first_frame, last_frame) -> tuple:
        if first_frame > self.last_frame():
            return ()
        return self._frame_index_in_data(first_frame), self._frame_index_in_data(
            last_frame
        )

    def last_frame(self) -> int:
        return self.start_frame + self.frame_data.data.shape[0]


class FrameDataCollection:
    """Class to store a collection of (:func:`~pandablocks.connections.FrameData`) objects
    and allow a set of frames to be retrieved 

    * Add frames contained in FrameData object using :func:`~add_data`
    * Retrieve frames using :func:`get_data`

    """
    def __init__(self):
        self.data_collection: list[FrameNumberAndData] = []
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_column_names(self) -> tuple[str, ...]:
        if len(self.data_collection) == 0:
            return ()
        return self.data_collection[0].frame_data.column_names

    def get_num_frames(self) -> int:
        if len(self.data_collection) == 0:
            return 0
        return self.data_collection[-1].last_frame()

    def _find_frame_location(self, frame_number: int) -> int:
        """Find index of object in 'data_collection' list that contains
        frame with specified number

        Args:
            frame_number (int):

        Returns:
            int: index in data_collection list
        """
        # index in 'data_collection' list of specified frame number
        return [
            ind
            for ind, fn in enumerate(self.data_collection)
            if fn.start_frame <= frame_number
        ][-1]

    def add_data(self, start_frame: int, frame_data: FrameData):
        """Add a FrameData object to the data collection
        Args:
            start_frame (int): index of first frame in FrameData
            frame_data (FrameData):
        """
        self.data_collection.append(FrameNumberAndData(start_frame, frame_data))

    def _convert_to_dict(self, structured_ndarray: NDArray) -> dict[str, NDArray]:
        return {name: structured_ndarray[name] for name in self.get_column_names()}

    # Return frames of data
    def get_data(self, start_frame: int, end_frame: int) -> dict[str, NDArray]:
        """Return numpy arrays containing several frames of data
        (frame range excludes final specified frame)

        Args:
            start_frame (int):
            end_frame (int):

        Returns:
            dict[str, NDArray]: Numpy array containing (end_frame-start_frame + 1)
                frames of data for all available data fields
        """
        # Find indices in data_collection that contain start and end frame
        start_index = self._find_frame_location(start_frame)
        end_index = self._find_frame_location(end_frame - 1)
        self.logger.debug(f"Frame index range : {start_index} {end_index}")

        # Frame range is within single FrameNumberAndData
        if start_index == end_index:
            framedata = self.data_collection[start_index].get_frames(
                start_frame, end_frame
            )
            return self._convert_to_dict(framedata)

        # Frame range spans multiple FrameNumberAndDatas :

        # Extract partial set of frames from first and last FrameNumberAndData objects
        start_frames = self.data_collection[start_index].get_frames(start_frame, -1)

        start_frame_of_end = self.data_collection[end_index].start_frame
        end_frames = self.data_collection[end_index].get_frames(
            start_frame_of_end, end_frame
        )

        # make list of complete set of data
        framedata_list = [start_frames]
        for i in range(start_index + 1, end_index):
            framedata_list.append(self.data_collection[i].frame_data.data)
        framedata_list.append(end_frames)

        # Combine to single NDArray
        data = np.concatenate(framedata_list)

        # Convert from structured array to dict
        # NB: NDArrays in the dict are views into the original data, not copies
        return self._convert_to_dict(data)


class SocketDatasource(Datasource):
    def __init__(self, ip_address: str, data_port=8889):
        self.ip_address = ip_address
        self.data_port = data_port
        self.scaled_data = False
        self.collected_data = FrameDataCollection()
        self.data_names = []  # Names of all the data captured (from stream header)
        self.poll_interval_secs: float = 0.1
        self.collection_finished = False
        self.collection_running = False
        self.socket_max_readsize_kb = 10 * 1024
        self._tcp_socket: socket.socket | None = None
        self._data_connection: DataConnection | None = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def configure_source(self, source_path: str):
        # Nothing to be done here
        pass

    def connect(self):
        self.logger.info(
            f"Connecting to Panda TCP socket : ip address = {self.ip_address}, "
            f"port = {self.data_port}"
        )
        self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_socket.connect((self.ip_address, self.data_port))

        self._data_connection = DataConnection()
        connection_commands = self._data_connection.connect(self.scaled_data)
        self._tcp_socket.sendall(connection_commands)
        ## need to make sure the data names are available immediately after connection
        self.collect_in_thread()

    def is_connected(self) -> bool:
        return self._tcp_socket is not None

    def close(self):
        if self._tcp_socket is not None:
            self._tcp_socket.close()

    def collect_in_thread(self):
        self._collection_thread = Thread(target=self.collect_data)
        self._collection_thread.start()
        self.logger.info("Waiting for data names to be read from stream")
        while len(self.data_names) == 0:
            sleep(0.1)
        self.logger.info("Stream ready")

    def collect_data(self):
        if self.collection_running:
            raise RuntimeError(
                "Cannot run 'collect_data' collection again - it is already running"
            )

        try:
            self.collection_running = True
            self._run_data_collection_loop()
        except Exception as ex:
            self.logger.error(f"Caught exception : {ex}")
        self.collection_finished = True
        self.collection_running = False

    def _run_data_collection_loop(self):
        if self._tcp_socket is None or self._data_connection is None:
            raise RuntimeError(f"Cannot collect data - 'connect' has not been called "
                               f"on SocketDatasource for {self.ip_address}")

        self.collection_running = True
        self.collection_finished = False
        self.collected_data = FrameDataCollection()
        self.logger.info("Started collecting data from socket...")
        start_frame = 0
        while not self.collection_finished:
            # Repeatedly process bytes from the PandA looking for data
            received = self._tcp_socket.recv(self.socket_max_readsize_kb * 1024)
            self.logger.debug(f"{len(received)} bytes received")

            for data in self._data_connection.receive_bytes(
                received, flush_every_frame=True
            ):
                dtype = type(data)
                if dtype is FrameData:
                    fdata = typing.cast(FrameData, data)
                    self.collected_data.add_data(start_frame, fdata)
                    start_frame += fdata.data.shape[0]
                elif dtype is StartData:
                    self.extract_data_names(typing.cast(StartData,data))
                elif dtype is EndData:
                    self.logger.info("Collection finished")
                    self.collection_finished = True
                else:
                    print(f"{dtype} : {data}")
            sleep(self.poll_interval_secs)

    def extract_data_names(self, start_data: StartData):
        self.logger.debug(f"Extracting data names from stream header : {start_data}")
        self.data_names = ["ALL"]
        for f in start_data.fields:
            self.data_names.append(f"{f.name}.{f.capture}")
        self.logger.info(f"Names of fields in data socket stream : {self.data_names}")

    def get_num_frames(self) -> int:
        return self.collected_data.get_num_frames()

    def set_data_names(self, dataset_names: list[str]):
        # Nothing to be done here
        pass

    def has_dataset(self, name) -> bool:
        return name in self.data_names

    def read_data(self, start_frame: int, end_frame: int) -> dict[str, NDArray]:
        self.logger.debug(f"Reading frames : {start_frame}, {end_frame}")
        dat = self.collected_data.get_data(start_frame, end_frame)
        self.logger.debug(f"{dat}")
        return dat


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

        self.h5_file = File(
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
            raise Exception(
                "Cannot read from Hdf data source - not connected to any file"
            )

    def close(self):
        if self.h5_file is not None:
            self.logger.info(
                f"Closing read connection to hdf file {self.h5_file.filename}"
            )
            self.h5_file.close()
            self.h5_file = None
            self.h5_datasets = {}

    def get_num_frames(self) -> int:
        self._setup_datasets()
        if len(self.h5_datasets) == 0:
            return -1

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
            # already have the dataset, nothing to do
            if name in self.h5_datasets:
                continue

            # check it exists
            if name not in self.h5_file.keys():
                raise ValueError(
                    f"Could not find dataset called {name} in hdf file {self.file_path}"
                )

            # check it's a Dataset (and not a Group or Datatype)
            dataset = self.h5_file[name]
            if type(dataset) is not Dataset:
                raise ValueError(
                    f"Cannot read data called '{name}' from {self.file_path} "
                    "- it is not a Dataset"
                )

            self.h5_datasets[name] = dataset
        self.logger.info(f"Datasets for {self.file_path} : {self.dataset_names}")

    def read_data(self, start_frame: int, end_frame: int) -> dict[str, NDArray]:
        if len(self.dataset_names) == 0:
            raise ValueError(
                "Cannot read data - names of datasets to be read "
                "have not been set using 'set_data_names'"
            )

        self._setup_datasets()
        num_frames = end_frame - start_frame
        data = {}
        for name in self.dataset_names:
            dset = self.h5_datasets[name]
            dset.refresh()
            dataset = dset[start_frame : end_frame + 1]

            # make sure we have correct number of frames and truncate
            # elements in outermost dimension if necessary
            # (sometimes there are more - SWMR flush/readback race condition?)
            if dataset.shape[0] != num_frames:
                dataset = dataset[:num_frames]

            data[name] = dataset

        return data


def test_frame_data_collection():
    fdc = FrameDataCollection()
    num_frames = 5
    shape = (num_frames, 1)
    num_datasets = 10
    orig_datasets: list[NDArray] = []
    data_name = "COUNTER1.OUT.Value"
    for i in range(0, num_datasets):
        # make array of random numbers, set the data name and type
        data = np.random.random(shape).astype(dtype=[(data_name, "<f8")])
        orig_datasets.append(data)
        fdc.add_data(i * shape[0], FrameData(data))

    # check number of frames across all datasets is correct
    assert fdc.get_num_frames() == shape[0] * num_datasets

    # test we can extract original datasets
    for i in range(0, num_datasets):
        orig = orig_datasets[i][data_name]
        arr2 = fdc.get_data(i * num_frames, (i + 1) * num_frames)[data_name]
        assert np.array_equal(orig, arr2), (
            f"Extracted array :\n {arr2}\n is not same as original :\n{orig}!"
        )

    # test we can extract frames across 2 datasets
    for i in range(0, num_datasets, 2):
        orig = np.concat([orig_datasets[i], orig_datasets[i + 1]])[data_name]
        start_frame = i * num_frames
        end_frame = start_frame + 2 * num_frames
        arr2 = fdc.get_data(start_frame, end_frame)[data_name]
        assert np.array_equal(orig, arr2), (
            f"Extracted array :\n {arr2}\n is not same as original :\n{orig}!"
        )
