import asyncio
import logging
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
)

FUNCTION_REGISTRY = {
    "value": lambda *vals: vals[0],
    "add": np.add,
    "subtract": np.subtract,
    "multiply": np.multiply,
    "divide": np.divide,
    "log": np.log,
    "lni0it": lambda *vals: np.log(vals[0], vals[1]),
}


@dataclass
class ProcessorJob:
    start_time: str
    task: Task
    processor: Processor
    setup: ProcessorSetup

    def get_status(self) -> dict[str, str]:
        return {
            "start_time": self.start_time,
            "state": self.processor.get_state().name,
            "num_frames": str(self.processor.get_frame_number()),
        }


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
            " is not recognised"
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
    print(f"start_processor called : {setup}")
    print(f"Type : {type(setup)}")

    check_file_exists("Input file", setup.input_file)

    hdf_datasource = HdfDatasource()
    hdf_datasource.configure_source(setup.input_file)

    hdf_writer = HdfDataWriter(setup.output_file)

    processing_config = [to_processing_config(step) for step in setup.processor_outputs]

    processor = Processor(
        hdf_datasource,
        processing_config,
        hdf_writer,
        no_new_data_timeout=setup.no_new_data_timeout,
        process_loop_sleep_secs=setup.process_loop_sleep_secs,
    )

    async def async_wrapper():
        try:
            await asyncio.to_thread(processor.start_processing)
        except Exception as e:
            print(f"Processing failed: {e}")

    timestamp = datetime.now().strftime("%Y-%m-%d %X")

    task = asyncio.create_task(async_wrapper())
    task_id = str(id(task))
    tasks[task_id] = ProcessorJob(
        task=task, processor=processor, setup=setup, start_time=timestamp
    )
    return task_id


@app.put("/stop_task/{task_id}")
async def stop_task(task_id: str) -> dict[str, str]:
    get_task(task_id).processor.end_data_loop = True
    return {"status": ProcessorState.STOPPING.name}


@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str) -> dict[str, str]:
    print(f"get_processor_state : {task_id}")
    return get_task(task_id).get_status()


@app.get("/task_status")
async def get_all_task_status() -> dict[str, dict[str, str]]:
    return {task_id: job.get_status() for task_id, job in tasks.items()}


@app.get("/all_tasks/")
async def get_all_tasks() -> dict[str, Any]:
    return {task_id: job.setup for task_id, job in tasks.items()}
