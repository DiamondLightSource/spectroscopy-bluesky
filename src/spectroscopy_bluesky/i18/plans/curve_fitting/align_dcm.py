import bluesky.plan_stubs as bps
import event_model
from dodal.common import inject
from dodal.common.types import MsgGenerator
from dodal.devices import DCM
from dodal.devices.i18.diode import Diode

DEFAULT_DCM: DCM = inject("dcm")
DEFAULT_DIODE: Diode = inject("d7diode")


def align_dcm(
    dcm=DEFAULT_DCM, diode: Diode = DEFAULT_DIODE, sim: bool = False
) -> MsgGenerator:  # noqa: E501
    """

    sample stages T1X
    T1Y

    (for tomography also T1Theta)

    two ion chambers

    kb motors, two mirrors vertical and horizontal
    ecah has 2 motors, bend1, bend2
    usually moved simultaneously, but for fine focus separately

    get the gaussian shape IT transmission detector we get the shape


    first, we lookup table - calibrate the DCM
    - measure foil, etc Fe, Mg, then absorption spectrum
    then the xanes absorption - then derivative, argmax of the first derivative
    then Bragg offset is adjusted to match the calibrated value

    second the idgap lookup tables
    - for 10-15 points inside the energy range for this element
    we scan the gap fo the insertion devise, looking for the maximum
    then quadratic interpolation, written into the file,
    then GDA probably some interpolation
    TFG calculates frequency from current via voltage
    so we need to load the panda configuration

    align the pinhole to reduce the scatter -
    400 micron or 200 micron, then centralize it
    usuallly not seen immediately
    FocusingMirror misses curvature
    preparation for the wire stage - check if we have any
    gold wires on the sample stage - scanned in one direction
    first horizonal, vertical
    then record with IT the absorption profile, derviative and fitting
    then changing the bend
    could be 10 iterations, in either direction
    to minimuze the beam size until it changes
    to see the beam shape and the size
    takes usually 30 minutes to go through focusing manually, 2-3 hours

    visual comparison fo the drviative -
    best if without the tails, could be parametrized
    or 50 micron beam - and then defocus to get to that

    golden plate with wires is moved by some other location


    """

    if sim:
        # use patterngenerator
        # make the undulator gap motor to be something virutal
        pass
        # todo will need a device like this https://github.com/DiamondLightSource/dodal/blob/e163f793c0c35fda6a2caf2dc9fb68b45a62971e/src/dodal/devices/zocalo/zocalo_results.py#L111
        # d = event_model.ComposeDescriptor()
        # e = event_model.ComposeEvent()

    else:
        yield from bps.read(diode)
        # use bragg motor
        # dcm.bragg_in_degrees

    yield from {}
