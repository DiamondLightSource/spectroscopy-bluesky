from blueapi.service.model import TaskRequest
from blueapi.worker.event import TaskError
from daq_queuing_service.external_interaction.blueapi.blueapi_call import (
    BlueapiCall,
    BlueapiCallResponse,
)
from daq_queuing_service.log import (
    LOGGER,
    add_session_to_logger,
)
from daq_queuing_service.plugins.converter import Converter
from daq_queuing_service.task_queue.task import (
    Task,
    TaskWithPosition,
)


class P51Converter(Converter):
    def __init__(self):
        pass

    def pre_process(
        self,
        current_task: TaskWithPosition | None,
        queue: list[Task],
        history: list[TaskWithPosition],
        call_history: list[BlueapiCallResponse],
    ) -> list[Task]:
        return queue

    def construct_blueapi_calls(
        self,
        queue: list[TaskWithPosition],
        history: list[TaskWithPosition],
        call_history: list[BlueapiCallResponse],
    ) -> list[BlueapiCall]:
        call_list: list[BlueapiCall] = []

        for task in queue:
            with add_session_to_logger(task.experiment.instrument_session):
                match task.experiment:
                    case TaskRequest():
                        call_list.append(
                            BlueapiCall(
                                task_request=task.experiment, parent_task_id=task.id
                            )
                        )
        return call_list

    def pause_on_fail_blueapi_call(
        self, call: BlueapiCall, errors: list[str | TaskError] | None
    ) -> bool:

        for error in errors or []:
            if isinstance(error, TaskError):
                LOGGER.warning(
                    "Failed to execute task" + "Continuing with the rest of the queue"
                )
                return False
        return True
