import asyncio
import logging
import traceback
import uuid
from asyncio import Task
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException

from spectroscopy_bluesky.common.processing_service import (
    HdfDatasource,
    HdfDataWriter,
    Processor,
    ProcessorFunctionOutput,
    ProcessorOutput,
    ProcessorSetup,
    ProcessorState,
    SocketDatasource,
)


def log_i0_it(i0, it):
    ratio = i0 / it
    zeros = np.zeros_like(i0, dtype=float)
    val = np.log(ratio, where=(ratio > 0), out=zeros)
    return val


def ff_i0(detector_ff, i0):
    # multiply 2d detector ff for each det element by 1d i0 counts
    # (converting 1d i0 array to 2d with inner dimension = 1)
    return detector_ff * i0[:, None]


FUNCTION_REGISTRY = {
    "value": lambda *vals: vals[0],
    "add": np.add,
    "subtract": np.subtract,
    "multiply": np.multiply,
    "divide": np.divide,
    "log": np.log,
    "lni0it": log_i0_it,
    "ffi0": ff_i0,
}


@dataclass
class ProcessorJob:
    start_time: str
    task: Task
    processor: Processor
    setup: ProcessorSetup

    def get_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "start_time": self.start_time,
            "state": self.processor.get_state().name,
            "num_frames": str(self.processor.get_frame_number()),
        }
        if self.processor.error_message is not None:
            status["error_message"] = self.processor.error_message
            status["error_traceback"] = self.processor.error_traceback
        return status


tasks: dict[str, ProcessorJob] = {}


def get_task(task_id: str) -> ProcessorJob:
    if task_id not in tasks:
        raise HTTPException(
            status_code=404, detail=f"Task with task_id = {task_id} was not found"
        )
    return tasks[task_id]


logging.basicConfig(
    level=logging.DEBUG,  # capture DEBUG and above
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def to_processing_config(processing_step: ProcessorOutput) -> ProcessorFunctionOutput:
    # lookup the function reference to use
    if processing_step.function_name not in FUNCTION_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Processing function name '{processing_step.function_name}'"
            " is not recognised",
        )

    p = ProcessorFunctionOutput(
        output_path=processing_step.output_path,
        function=FUNCTION_REGISTRY[processing_step.function_name],
        data_names=processing_step.data_names,
    )
    return p


def check_file_exists(msg_prefix: str, file_path: str):
    if not Path(file_path).exists():
        raise HTTPException(
            status_code=404, detail=f"{msg_prefix} '{file_path}' could not be accessed"
        )


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.put("/start_processor")
async def start_processor(setup: ProcessorSetup):
    logging.info(f"start_processor called : {setup}")

    datasources = []
    for source_name in setup.input_files:
        if source_name.endswith((".hdf5", ".h5")):
            # hdf file data source
            logging.info(f"Making HdfDatasource for : {source_name}")
            check_file_exists("Input file", source_name)
            datasource = HdfDatasource()
            datasource.configure_source(source_name)
            datasources.append(datasource)
        else:
            # panda TCP socket
            logging.info(f"Making SocketDatasource for : {source_name}")
            datasource = SocketDatasource(ip_address=source_name)
            datasources.append(datasource)

    hdf_writer = HdfDataWriter(setup.output_file)

    processing_config = [to_processing_config(step) for step in setup.processor_outputs]
    logging.info(f"Processing config : {processing_config}")
    processor = Processor(
        datasources,
        processing_config,
        hdf_writer,
        no_new_data_timeout=setup.no_new_data_timeout,
        process_loop_sleep_secs=setup.process_loop_sleep_secs,
    )

    async def async_wrapper():
        try:
            await asyncio.to_thread(processor.start_processing)
        except Exception as e:
            logging.error(
                f"Processing failed: {e}. Traceback : {traceback.format_exc()}"
            )

    timestamp = datetime.now().strftime("%Y-%m-%d %X")

    task = asyncio.create_task(async_wrapper())
    task_id = str(uuid.uuid4())
    tasks[task_id] = ProcessorJob(
        task=task, processor=processor, setup=setup, start_time=timestamp
    )
    return task_id


@app.put("/stop_task/{task_id}")
async def stop_task(task_id: str) -> dict[str, str]:
    get_task(task_id).processor.end_data_loop = True
    return {"status": ProcessorState.STOPPING.name}


@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str) -> dict[str, Any]:
    return get_task(task_id).get_status()


@app.get("/task_status")
async def get_all_task_status() -> dict[str, dict[str, Any]]:
    return {task_id: job.get_status() for task_id, job in tasks.items()}


@app.get("/all_tasks/")
async def get_all_tasks() -> dict[str, Any]:
    return {task_id: job.setup for task_id, job in tasks.items()}
