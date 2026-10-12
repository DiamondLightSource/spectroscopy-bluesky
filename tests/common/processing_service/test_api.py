import re
from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

import spectroscopy_bluesky.common.processing_service.api as api
from spectroscopy_bluesky.common.processing_service.api_models import (
    ProcessorOutput,
    ProcessorSetup,
)

client = TestClient(api.app)
client_no_exceptions = TestClient(api.app, raise_server_exceptions=False)


@pytest.fixture
def processor_setup():
    return ProcessorSetup(
        input_files=["1.h5"],
        output_file="2.h5",
        processor_outputs=[
            ProcessorOutput(
                output_path="new_data", function_name="value", data_names=["orig_data"]
            )
        ],
    )


def test_bad_panda_connection(processor_setup: ProcessorSetup):
    panda_ip_address = "panda-ip-address"
    processor_setup.input_files = [panda_ip_address]
    response = client_no_exceptions.put(
        "/start_processor", json=processor_setup.model_dump()
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert re.match(
        f".*Problem connecting to \\'{panda_ip_address}\\'.*", response.json()["detail"]
    )


def test_health():
    response = client.get("/health")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_bad_task_id():
    response = client.put("/stop_task/1")
    print(response.text)
    assert response.status_code == 404
    assert re.match("Task.*was not found", response.json()["detail"])


def test_start_processor(processor_setup: ProcessorSetup):
    response = client.put("/start_processor", json=processor_setup.model_dump())
    print(response.text)
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert re.match("Input file.*could not be accessed", response.json()["detail"])


def test_processor_args(mocker: MockerFixture, processor_setup: ProcessorSetup):
    validate_processor_args(mocker, processor_setup)


def validate_processor_args(mocker: MockerFixture, setup: ProcessorSetup):

    mock_path = api.__name__  # path tp api module

    mocker.patch(f"{mock_path}.check_file_exists")
    mock_processor: MagicMock = mocker.patch(f"{mock_path}.Processor", autospec=True)

    mock_hdf = MagicMock()
    mock_hdf_source = mocker.patch(f"{mock_path}.HdfDatasource")
    mock_hdf_source.return_value = mock_hdf

    mock_hdf_writer = MagicMock()
    mock_hdf_output = mocker.patch(f"{mock_path}.HdfDataWriter")
    mock_hdf_output.return_value = mock_hdf_writer

    client.put("/start_processor", json=setup.model_dump())

    mock_processor.assert_called_once()

    args, kwargs = mock_processor.call_args
    assert args[0] == [mock_hdf]

    # convert serializable ProcessorOutput to ProcessorFunctionOutput
    # passed to Processor class
    proc_func_output = api.to_processing_config(setup.processor_outputs[0])
    assert args[1] == [proc_func_output]

    assert args[2] == mock_hdf_writer

    assert kwargs == {
        "no_new_data_timeout": setup.no_new_data_timeout,
        "process_loop_sleep_secs": setup.process_loop_sleep_secs,
    }
