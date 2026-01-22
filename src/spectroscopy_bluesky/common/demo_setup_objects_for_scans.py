import asyncio
import socket

from bluesky.callbacks.best_effort import BestEffortCallback
from bluesky.plans import scan
from bluesky.protocols import Movable
from bluesky.run_engine import RunEngine
from ophyd.sim import det, motor
from ophyd_async.core import AsyncStatus, StandardReadable, init_devices
from ophyd_async.epics.motor import Motor
from ophyd_async.sim import SimMotor, SimPointDetector


def run_test_scan(detector, motor):
    yield from scan([detector], motor, -3, 3, 21)


# Setup the RunEngine and callbacks
RE = RunEngine()
bec = BestEffortCallback()
RE.subscribe(bec)

#### Scan using ophyd simulated motor and detector

RE(scan([det], motor, -3, 3, 21))


#### Scan using ophyd-async simulated devices

sim_motor = SimMotor("sim_motor")
sim_det = SimPointDetector(None, num_channels=1, name="sim_det")
RE(run_test_scan(sim_det, sim_motor))


### Scan using ophyd-asunc motor with mock Epics backend

# Initialise ophyd-async Motor devices using mock Epics signals
# (using mock=True parameter)
with init_devices(mock=True):
    epics_sim_motor = Motor("mock_signal", name="epics_sim_motor")

RE(run_test_scan(sim_det, epics_sim_motor))


#### Scan using ophyd-async motors with real (channel access) backend

# make PV base name for simulated Epics motor
# NB : need to have simulated Epics motors running and environment variable
# EPICS_CA_SERVER_PORT=6064 set for this to work!
hostname = socket.gethostname().split(".")[0]
pv_base = hostname + "-MO-SIM-01"

# Initialise ophyd-async Motor connect to real Epics signals
with init_devices():
    epics_motor = Motor(pv_base + ":M1", "epics_sim_motor")

RE(run_test_scan(sim_det, epics_motor))


#### Scan using using implementation of StandardReadable,
# Moveable object that moves two motors


# Make a new class that controls two motors
class TwoMotors(StandardReadable, Movable[float]):
    def __init__(self, pv1: str, pv2: str, name: str = ""):
        with self.add_children_as_readables():
            self.motor1 = Motor(pv1, name="motor1")
            self.motor2 = Motor(pv2, name="motor2")
        super().__init__(name=name)

    # the 'set' method needs to be implemented - part of Movable protocal.
    @AsyncStatus.wrap
    async def set(self, position_value: float):
        # Move motor1 and motor2 sequentially
        await self.motor1.set(position_value)
        await self.motor2.set(position_value * 2)

    async def async_move(self, position_value: float):
        # or move simultanously using asyncio.gather
        await asyncio.gather(
            self.motor1.set(position_value), self.motor2.set(position_value * 2)
        )


# Initialise and connect to real Epics signals
with init_devices():
    two_epics_motors = TwoMotors(
        pv_base + ":M1", pv_base + ":M2", name="two_epics_motors"
    )

RE(run_test_scan(sim_det, two_epics_motors))

# Run scan using single motor from two_epics_motors object
RE(run_test_scan(sim_det, two_epics_motors.motor1))
