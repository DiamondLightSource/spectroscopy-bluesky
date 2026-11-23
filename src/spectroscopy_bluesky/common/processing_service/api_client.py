import json
import logging
from time import sleep
from typing import Any

import requests
from pydantic import BaseModel


class ProcessingClient:
    def __init__(self, url):
        self.url = url
        self.monitor_poll_interval = 1.0
        self.logger = logging.getLogger(self.__class__.__name__)

    def put_request(self, endpoint: str, data: Any | None = None):
        self.logger.info(f"PUT to {endpoint}, json = {data}")
        resp = requests.put(self.url + endpoint, json=data)
        self.logger.info(f"Response = {resp}")
        return resp.json()

    def get_request(self, endpoint: str, json_data=None):
        if json_data is not None:
            json_str = json.dumps(json_data)
            print(json_str)
        self.logger.info(f"GET from {endpoint}")
        resp = requests.get(self.url + endpoint, params=json_data)
        return resp.json()

    def start_processor(self, setup: BaseModel) -> str:
        return self.put_request("start_processor", setup.model_dump())

    def get_task_status(self, task_id: str) -> dict[str, str]:
        return self.get_request(f"task_status/{task_id}")

    def stop_task(self, task_id: str) -> dict[str, str]:
        return self.put_request(f"stop_task/{task_id}")

    def wait_monitor_processor(self, task_id: str):
        print(f"Monitoring task id {task_id}")
        finished = False
        while not finished:
            status = self.get_task_status(task_id)  # ["num_frames"]
            print(f"status = {status}")
            if "state" not in status:
                finished = True
            sleep(self.monitor_poll_interval)
            finished = "FINISHED" in status["state"]
