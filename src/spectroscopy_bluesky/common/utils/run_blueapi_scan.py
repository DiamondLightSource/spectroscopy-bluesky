from blueapi.client.client import BlueapiClient
from blueapi.client.event_bus import AnyEvent
from blueapi.config import ApplicationConfig, RestConfig, StompConfig, TcpUrl

from blueapi.service.model import TaskRequest
from bluesky_stomp.models import BasicAuthentication

control_machine_url = "http://i20-1-control.diamond.ac.uk:8000"
stomp_url = "tcp://j20-rabbitmq.diamond.ac.uk:61613"
# session="/dls/i20-1/data/2023/cm33897-5"
session = "cm33897-5"

app_config = ApplicationConfig(
    stomp=StompConfig(
        enabled=True,
        url=TcpUrl(stomp_url),
        auth=BasicAuthentication(username="i20-1", password="Tw9h2Qsx5UGHs"),
    ),
    api=RestConfig(url=control_machine_url),
)

def on_event(event: AnyEvent):
    print(f"Callback : {event}")


def create_task(plan_name, session, **kwargs):
    return TaskRequest(
        name=plan_name,
        params=dict(**kwargs),
        instrument_session=session,
    )

def run_plan(
    plan_name,
    session="cm33897-5",
    block=True,
    config: ApplicationConfig = app_config,
    **kwargs,
):
    task = create_task(plan_name, session, **kwargs)

    # make new client, to avoid multiple messages being received per scan event
    # from leftover subscriptions
    client = BlueapiClient.from_config(config)

    if not block:
        return client.create_and_start_task(task)

    resp = client.run_task(task, on_event=on_event)
    if resp.task_status is not None and not resp.task_status.task_failed:
        print("Plan Succeeded")


# run_plan("set_absolute", movable="turbo_slit_x", value=5)
