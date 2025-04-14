from ophyd_async.core import StandardReadable
from ophyd_async.epics.core import epics_signal_r, epics_signal_rw


class D7Positioner(StandardReadable):
    def __init__(self, prefix: str, name: str = ""):
        self._prefix = prefix
        with self.add_children_as_readables():
            self.setpoint = epics_signal_rw(float, prefix + ":SELECT")
            self.readback = epics_signal_r(float, prefix + ":SELECT")
            self.done = epics_signal_r(float, prefix + ":DMOV")
            self.stop = epics_signal_rw(bool, prefix + ":STOP.PROC")
        super().__init__(name=name)


# pv_prefix = "ws416-MO-SIM-01:M2"
# # pv_prefix = "SR18I-MO-SERVC-01:BLGAPMTR"

# d7FilterPositioner = D7Positioner("BL18I-DI-PHDGN-07:A:MP", name="d7FilterPositioner")
# d7DiodePositioner = D7Positioner("BL18I-DI-PHDGN-07:B:MP", name="d7DiodePositioner")

# epics_motor = EpicsMotor(pv_prefix, name="epics_motor")

# bec = BestEffortCallback()
# RE = RunEngine()
# RE.subscribe(bec)

# RE(scan([simple_positioner], simple_positioner, 1, 10, 10))
# RE(scan([epics_motor], epics_motor, 1, 10, 10))
