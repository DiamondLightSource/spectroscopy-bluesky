import json
import pathlib

import pytest

from spectroscopy_bluesky.common.devices.spectrometer.xes_spectrometer import XesCalculator


def read_file(relative_path: str) -> dict[str, str]:
    full_path = pathlib.Path(__file__).parent / relative_path
    file = open(full_path.resolve())
    with file:

        all_lines = " ".join(file.readlines())
        return json.loads(str(all_lines))


def compare_positions(xes_calculator: XesCalculator, filename: str, angle: float, index_range: int):
    print(f"Testing {filename}")
    correct_vals = read_file(filename)
    suffixes = "X", "Y", "Rot", "Pitch"
    # for prefix, index in ("minus",-1), ("centre", 0), ("plus", 1) :
    for index in range(-index_range, index_range+1):
        val=str(abs(index))
        if index < 0:
            prefix = "minus"+val
        elif index > 0:
            prefix = "plus"+val
        else:
            prefix = "centre"

        positions = xes_calculator.calculate_analyser_position(angle, index)
        for suffix, val in zip(suffixes, positions, strict=True) : 
            dict_key = prefix+suffix
            assert val == pytest.approx(correct_vals[dict_key]), f"{dict_key} value is incorrect"

    positions = xes_calculator.calculate_detector_position(angle)
    for index, dict_key in enumerate(["detX", "detY", "detRot"]):
        assert positions[index] == pytest.approx(correct_vals[dict_key]), f"{dict_key} value is incorrect"

    print("Done")

filename="xes_test_positions/3analyser_positions_65.0.txt"
vals = read_file(filename)
print(vals.keys())

@pytest.mark.parametrize(
    "angle",
    [ 65.0, 70.0, 75.0, 80.0, 85.0  ]
)
def test_3_analyser_xes(angle: float) :
    xes_calculator = XesCalculator(1000.0)
    filename=f"xes_test_positions/3analyser_positions_{angle:.1f}.txt"
    compare_positions(xes_calculator, filename, angle, 1)


@pytest.mark.parametrize(
    "angle",
    [ 65.0, 70.0, 75.0, 80.0, 85.0  ]
)
def test_7_analyser_upper_xes(angle: float) :
    xes_calculator = XesCalculator(1000.0)
    xes_calculator.horizontal_offset = 130.0
    xes_calculator.detector_axis_angle = -20.0
    filename=f"xes_test_positions/7analyser_positions_upper_{angle:.1f}.txt"
    compare_positions(xes_calculator, filename, angle, 1)
