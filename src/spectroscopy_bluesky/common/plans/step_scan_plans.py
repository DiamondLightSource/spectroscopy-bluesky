from collections.abc import Mapping
from typing import Any

import bluesky.plans as bp
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator
from dodal.plan_stubs.data_session import attach_data_session_metadata_decorator
from ophyd_async.epics.motor import Motor

"""
Dictionary of scan arguments from motor scan_args (start, stop, steps)
"""


def make_args(motor, scan_args, prefix=""):
    return {
        "motor" + prefix: motor,
        "start" + prefix: scan_args[0],
        "stop" + prefix: scan_args[1],
        "steps" + prefix: int(scan_args[2]),
    }

@attach_data_session_metadata_decorator()
def step_scan(
    detectors: list[Readable],
    motor: Motor,
    scan_args: list[object],
    metadata: dict[str, Any] | None = None,
) -> MsgGenerator:
    """
    Scan wrapping `bp.scan`

    Args:
        detectors: List of readable devices, will take a reading at each point
        motor: name of motor to be moved
        scan_args: [start, stop, step]
        metadata
    """

    args = make_args(motor, scan_args)

    _md_ = {
        "plan_args": {
            "detectors": list(map(repr, detectors)),
            "*args": {k: repr(v) for k, v in args.items()},
        },
        "plan_name": "step_scan",
        **(metadata or {}),
    }

    yield from bp.scan([*detectors], *args.values(), md=_md_)

@attach_data_session_metadata_decorator()
def grid_scan(
    detectors: list[Readable],
    motor1: Motor,
    scan_args1: list[object],
    motor2: Motor,
    scan_args2: list[object],
    metadata: Mapping[str, Any] | None = None,
    snake_axes: bool | None = None,
) -> MsgGenerator:
    """
    Scan wrapping `bp.grid_scan'
        Args:
        detectors: List of readable devices, will take a reading at each point
        motor1: name of motor to be moved (outer axis of scan)
        scan_args1: [start, stop, step]
        motor2: name of motor to be moved (inner axis of scan)
        scan_args2: [start, stop, step]
        snake_axes:
        metadata
    """
    args1 = make_args(motor1, scan_args1, "1")
    args2 = make_args(motor2, scan_args2, "2")

    _md_ = {
        "plan_args": {
            "detectors": list(map(repr, detectors)),
            "*args1": {k: repr(v) for k, v in args1.items()},
            "*args2": {k: repr(v) for k, v in args2.items()},
        },
        "plan_name": "step_scan",
        **(metadata or {}),
    }

    yield from bp.grid_scan(
        detectors, *args1.values(), *args2.values(), md=_md_, snake_axes=snake_axes
    )
