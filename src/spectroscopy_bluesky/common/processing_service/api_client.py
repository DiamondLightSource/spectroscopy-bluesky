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

    def put_request(self, endpoint: str, json_data: Any | None = None):
        self.logger.info(f"PUT to {endpoint}, json = {json_data}")
        resp = requests.put(self.url + endpoint, json=json_data)
        self.logger.info(f"Response = {resp.json()}")
        return resp.json()

    def get_request(self, endpoint: str, json_data=None):
        self.logger.info(f"GET from {endpoint}, json = {json_data}")
        resp = requests.get(self.url + endpoint, params=json_data)
        self.logger.info(f"Response = {resp.json()}")
        return resp.json()

    def start_processor(self, setup: BaseModel) -> str:
        return self.put_request("start_processor", setup.model_dump())

    def get_task_status(self, task_id: str) -> dict[str, str]:
        return self.get_request(f"task_status/{task_id}")

    def stop_task(self, task_id: str) -> dict[str, str]:
        return self.put_request(f"stop_task/{task_id}")

    def wait_monitor_processor(self, task_id: str):
        self.logger.info(f"Monitoring task id {task_id}")
        finished = False
        while not finished:
            status = self.get_task_status(task_id)
            self.logger.info(f"status = {status}")
            if "state" not in status:
                finished = True
            sleep(self.monitor_poll_interval)
            finished = "FINISHED" in status["state"]
