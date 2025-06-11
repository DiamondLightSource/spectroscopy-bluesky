import bluesky.plan_stubs as bps
import pandas as pd
import numpy as np
from dodal.common.coordination import inject
from dodal.common.types import MsgGenerator
from dodal.devices.diode import D7Diode, Diode

DEFAULT_DCM: DCM = inject("dcm")
DEFAULT_DIODE: Diode = inject("d7diode")


def align_dcm(
    dcm=DEFAULT_DCM, diode: D7Diode = DEFAULT_DIODE, sim: bool = False
) -> MsgGenerator:  # noqa: E501
    """
    first, we lookup table - calibrate the DCM
    - measure foil, etc Fe, Mg, then absorption spectrum
    then the xanes absorption - then derivative, argmax of the first derivative
    then Bragg offset is adjusted to match the calibrated value

    - for 10-15 points inside the energy range for this element
    we scan the gap fo the insertion devise, looking for the maximum
    then quadratic interpolation, written into the file,
    then GDA probably some interpolation
    """
    # read previous values using the daq-config-server

    # take into account a specific harmonic
    data = pd.DataFrame(columns=["bragg", "id_gap", "diode_current"])
    bragg_range = np.linspace(0.1, 0.5, 10)  # example range for Bragg angle
    idgap_range = np.linspace(0.1, 0.5, 10)  # example range for ID gap
    # outer loop for the Bragg angle
    for angle in bragg_range:
        # set the Bragg angle
        yield from bps.mv(dcm.bragg, angle)

        # inner loop for the ID gap
        for gap in idgap_range:
            # set the ID gap
            yield from bps.mv(dcm.id_gap, gap)

            # measure the diode current
            yield from bps.sleep(1)
            top = yield from bps.rd(diode)
            data.loc[len(data)] = {
                "bragg": angle,
                "id_gap": gap,
                "diode_current": top.value,
            }
    # save the data to a file
    data.to_csv("alignment_data.csv", index=False)
    
