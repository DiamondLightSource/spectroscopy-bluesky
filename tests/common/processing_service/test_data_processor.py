import asyncio
import logging
from time import sleep

import numpy as np
import pytest
from h5py import Dataset, File
from numpy.typing import NDArray

from spectroscopy_bluesky.common.processing_service import (
    Datasource,
    HdfDatasource,
    HdfDataWriter,
    Processor,
    ProcessorFunctionOutput,
)
from spectroscopy_bluesky.common.processing_service.data_sources import (
    DataNotAvailableError,
    FrameData,
    FrameDataCollection,
)


@pytest.fixture
def temporary_test_directory(tmp_path):
    return str(tmp_path)


@pytest.fixture
def logi0it_config():
    return [
        ProcessorFunctionOutput(
            "index",
            lambda *vals: vals[0],
            ["index"],
        ),
        ProcessorFunctionOutput(
            "i0",
            lambda *vals: vals[0],
            ["scalar_0"],
        ),
        ProcessorFunctionOutput(
            "it",
            lambda *vals: vals[0],
            ["scalar_1"],
        ),
        ProcessorFunctionOutput(
            "lni0it",
            lambda *vals: calculate_log_i0_it(vals[0], vals[1]),
            ["scalar_0", "scalar_1"],
        ),
    ]


@pytest.fixture
def ffi0_config():
    return [
        ProcessorFunctionOutput(
            "i0",
            lambda *vals: vals[0],
            ["scalar_0"],
        ),
        ProcessorFunctionOutput(
            "FF",
            lambda *vals: vals[0],
            ["/entry/ff_values"],
        ),
        ProcessorFunctionOutput(
            "FFI0",
            lambda *vals: calculate_ffi0(vals[0], vals[1]),
            ["/entry/ff_values", "scalar_0"],
        ),
    ]


def calculate_log_i0_it(i0: NDArray, it: NDArray) -> NDArray:
    ratio = i0 / it
    zeros = np.zeros_like(i0, dtype=float)
    return np.log(ratio, where=(ratio > 0), out=zeros)


def calculate_ffi0_sum(ff_values: NDArray, i0: NDArray):
    rehaped_i0 = i0.reshape(i0.shape[0], 1)
    return np.sum(ff_values, axis=1) / rehaped_i0


def calculate_ffi0(ff_values: NDArray, i0: NDArray):
    reshaped_i0 = i0.reshape(i0.shape[0], 1)
    return ff_values / reshaped_i0


# Configure logging (do this once in your main entry point)
logging.basicConfig(
    level=logging.INFO,  # capture DEBUG and above
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def write_test_file(path: str, num_frames: int = 100):
    index = np.arange(0, num_frames, 1)
    vals = {
        "functions/index": index,
        "/functions/sin": np.sin(index / 10),
        "/functions/cos": np.cos(index / 10),
    }
    writer = HdfDataWriter(path)
    writer.add_data(vals)
    writer.close()


def write_test_xspress(
    path: str,
    num_frames: int = 10,
    num_writes: int = 10,
    num_channels: int = 10,
    write_sleep: float = 0.1,
):
    writer = HdfDataWriter(path)
    for count in range(num_writes):
        start_num = count * num_frames
        index = np.arange(start_num, start_num + num_frames, 1)
        scalers = np.zeros([num_frames, 10])
        for i in range(num_frames):
            scalers[i, :] = np.arange(i + start_num, i + start_num + num_channels, 1)

        vals = {
            "/entry/frame": index,
            "/entry/ff_values": scalers,
        }
        writer.add_data(vals)
        sleep(write_sleep)
    writer.close()


def write_test_ionchambers(
    path: str, num_frames: int = 10, num_writes: int = 10, write_sleep: float = 0.1
):
    writer = HdfDataWriter(path)
    for count in range(num_writes):
        start_num = count * num_frames
        index = np.arange(start_num + 0.1, start_num + num_frames, 1)
        vals = {
            "index": index,
            "scalar_0": np.sin(index / 10),
            "scalar_1": np.cos(index / 10),
            "scalar_2": np.tan(index / 10),
        }
        writer.add_data(vals)
        sleep(write_sleep)
    writer.close()


def run_processing(
    input_filepaths: list[str],
    output_filepath: str,
    processing_config: list[ProcessorFunctionOutput],
):
    data_sources: list[Datasource] = []
    for path in input_filepaths:
        source = HdfDatasource()
        source.configure_source(path)
        data_sources.append(source)

    hdf_writer = HdfDataWriter(output_filepath)
    processor = Processor(data_sources, processing_config, hdf_writer)
    processor.no_new_data_timeout = 0.25
    processor.process_loop_sleep_secs = 0.1
    processor.start_processing()


def start_file_writing(func, file: str, **args):
    default_args = {"num_frames": 100, "num_writes": 10, "write_sleep": 0.1}
    for k, v in default_args.items():
        if k not in args.keys():
            args[k] = v
    return asyncio.to_thread(func, file, **args)


async def start_processing(
    files_list, output_file, processing_config, sleep_time_secs=0.5
):
    async def process_data():
        await asyncio.sleep(sleep_time_secs)
        await asyncio.to_thread(
            run_processing,
            files_list,
            output_file,
            processing_config,
        )

    await process_data()


def get_dataset(hdf_file: File, name: str) -> Dataset:
    assert name in hdf_file.keys(), (
        f"Hdf file.{hdf_file.filename} name does not contain dataset {name}"
    )
    data = hdf_file[name]
    assert type(data) is Dataset
    return data


def get_datasets(hdf_file: File, *names) -> tuple[Dataset, ...]:
    datasets: list[Dataset] = []
    for name in names:
        datasets.append(get_dataset(hdf_file, name))
    return tuple(datasets)


def test_ffi0(temporary_test_directory, ffi0_config):
    ionchambers_file = str(temporary_test_directory + "/ionchambers.h5")
    detector_file = str(temporary_test_directory + "/detector.h5")
    output_file = str(temporary_test_directory + "/test_ffi0.h5")

    total_num_frames = 1000

    async def run_test():
        coro1 = start_file_writing(
            write_test_ionchambers,
            ionchambers_file,
            num_frames=total_num_frames // 10,
            num_writes=10,
            write_sleep=0.05,
        )
        coro2 = start_file_writing(
            write_test_xspress,
            detector_file,
            num_frames=total_num_frames // 10,
            num_writes=10,
            write_sleep=0.05,
        )
        coro3 = start_processing(
            [ionchambers_file, detector_file], output_file, ffi0_config
        )
        await asyncio.gather(coro1, coro2, coro3)

    asyncio.run(run_test())

    with File(output_file) as hdf_file:
        # check data is all present in file
        for name in [proc_config.output_path for proc_config in ffi0_config]:
            assert name in hdf_file.keys()

        def get_data(name: str) -> Dataset:
            assert type(name) is Dataset
            return hdf_file[name]

        # read data, check the shape matches expected number of frames
        i0_data, ff_data, ffi0_data = get_datasets(hdf_file, "i0", "FF", "FFI0")

        def test_data(data: Dataset, shape: tuple[int, ...]):
            assert data.shape == shape, f"{data.name} data is not correct shape"

        test_data(i0_data, (total_num_frames,))
        test_data(ff_data, (total_num_frames, 10))
        test_data(ffi0_data, (total_num_frames, 10))

        expected_ffi0 = calculate_ffi0(ff_data[:], i0_data[:])
        assert ffi0_data[:] == pytest.approx(expected_ffi0), (
            "Xspress, ionchamber FFI0 values"
        )


def test_hdf_source_file_not_found():
    source = HdfDatasource()
    source.file_timeout = 0.05
    source.file_path = "non_existant_file.h5"
    with pytest.raises(FileNotFoundError):
        source.connect()


def test_hdf_source_no_datasets(temporary_test_directory):
    file_path = temporary_test_directory + "/empty_file.h5"
    source = HdfDatasource()
    source.file_timeout = 0.05
    source.file_path = file_path
    with (
        File(file_path, mode="w", libver="latest"),
        pytest.raises(DataNotAvailableError),
    ):
        source.connect()


def test_start_processing_before_writing(temporary_test_directory, logi0it_config):
    ionchambers_file = str(temporary_test_directory + "/ionchambers.h5")
    output_file = str(temporary_test_directory + "/test_lns.h5")

    total_num_frames = 1000

    async def run_test():
        # create processing task - starts immediately
        run_processing = asyncio.create_task(
            start_processing([ionchambers_file], output_file, logi0it_config)
        )

        await asyncio.sleep(1.0)

        write_coro = start_file_writing(
            write_test_ionchambers,
            ionchambers_file,
            num_frames=total_num_frames // 10,
            num_writes=10,
            write_sleep=0.05,
        )

        await asyncio.gather(run_processing, write_coro)

    asyncio.run(run_test())


def test_ionchamber_lns(temporary_test_directory, logi0it_config):
    ionchambers_file = str(temporary_test_directory + "/ionchambers.h5")
    output_file = str(temporary_test_directory + "/test_lns.h5")

    total_num_frames = 1000

    async def run_test():
        coro1 = start_file_writing(
            write_test_ionchambers,
            ionchambers_file,
            num_frames=total_num_frames // 10,
            num_writes=10,
            write_sleep=0.05,
        )
        coro2 = start_processing([ionchambers_file], output_file, logi0it_config)
        await asyncio.gather(coro1, coro2)

    asyncio.run(run_test())

    with File(output_file) as hdf_file:
        # check data is all present in file
        for name in [proc_config.output_path for proc_config in logi0it_config]:
            assert name in hdf_file.keys()

        # check for and read data, check the type is correct
        index_data, i0_data, it_data, lni0it_data = get_datasets(
            hdf_file, "index", "i0", "it", "lni0it"
        )

        # check shape matches expected number of frames
        for data in i0_data, it_data, lni0it_data, index_data:
            assert data.shape == (total_num_frames,), (
                f"Ionchamber {data.name} data not correct shape"
            )

        # check calculated values
        expected_lnit0t = calculate_log_i0_it(i0_data[:], it_data[:])
        assert lni0it_data == pytest.approx(expected_lnit0t), "Ionchamber lnI0It values"


def test_hdf_writer(temporary_test_directory):
    file = str(temporary_test_directory + "/writer_test.hdf")
    total_num_frames = 100
    write_test_xspress(
        file, num_frames=total_num_frames // 10, num_writes=10, write_sleep=0
    )
    with File(file) as hdf_file:
        frame_index = get_dataset(hdf_file, "/entry/frame")
        assert frame_index == pytest.approx(np.arange(0, total_num_frames))

        ff_values = get_dataset(hdf_file, "/entry/ff_values")
        expected_ff_values = np.zeros([total_num_frames, 10])
        for i in range(total_num_frames):
            expected_ff_values[i, :] = np.arange(i, i + 10, 1)
        assert ff_values == pytest.approx(expected_ff_values)


def test_socket_frame_data_collection():
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
