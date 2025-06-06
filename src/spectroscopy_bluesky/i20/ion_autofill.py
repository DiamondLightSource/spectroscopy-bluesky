from dodal.common.coordination import inject
from dodal.common.types import MsgGenerator
from dodal.devices.tetramm import TetrammDetector


def ion_autofill(
    i0: TetrammDetector = inject("i0"),
    it: TetrammDetector = inject("iT"),
    iref: TetrammDetector = inject("iref"),
    i1: TetrammDetector = inject("i1"),
) -> MsgGenerator:
    # each has a valve and a pressure readout

    targetPressureAr = 35  # mbar
    targetPressureHe = 1800  # mbar

    ionchamber_purge_time = 20.00  # 30
    ionchamber_leak_wait_time = 10.0  # 10
    injection_equilibration_wait_time = 20
    helium_equilibration_wait_time = 10.0

    # there is one endpoint for argon injection, another for helium

    # inner plan
    def inject_from_valve(valve_number, target_pressure):
        pass
        # move mode to pressure control
        # open valve
        # wait for pressure to equilibrate
        # close valve
        # set mode to hold

    def purge(valve, pressure):
        # turn on the the vacuum pump - reset, open
        # open valve line valve
        # open valve
        # record base pressure
        # wait for the leak time
        # check the pressure again
        # if absolute pressure greater than 3 mbar, pring warning
        # close line valve
        # close main valve
        # turn off the vaccum pump - close

        pass

    yield from {}
