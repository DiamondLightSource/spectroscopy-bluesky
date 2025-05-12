import json
import math
import re
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from ophyd_async.core import StandardReadable
from pydantic import BaseModel
from src.spectroscopy_bluesky.i18.utils.stats import quadratic

from spectroscopy_bluesky.i18.devices.curve_fitting import (
    fit_quadratic_curve,
)


class LookupTableSettings(BaseModel):
    float_format: str = "%9.5f"
    sep: str = "\t"
    index: bool | None = None
    column_names: list[str] = ["Bragg [deg]", "ID gap [mm]"]


class BraggAngleToDistancePerpConverter:
    constant_top = 12.82991823
    constant_subtract = -0.33493688
    constant_inverse = 12.489

    def __init__(
        self, constant_top: float, constant_subtract: float, constant_inverse: float
    ):
        self.constant_top = constant_top
        self.constant_subtract = constant_subtract
        self.constant_inverse = constant_inverse

    def bragg_angle_degrees_to_distance(self, angle: float) -> float:
        return (self.constant_top / math.cos(angle / math.pi)) - self.constant_subtract

    def distance_mm_to_bragg_angle_degrees(self, distance: float) -> float:
        return self.constant_inverse / distance

    @staticmethod
    def create_from_file(path: Path) -> "BraggAngleToDistancePerpConverter":
        with open(path) as f:
            content = f.read()

        # Extract constants from ExpressionStoT
        sto_t_match = re.search(
            r"<ExpressionStoT>(\d+\.\d+)/cos\(X/.*?\)-(\d+\.\d+)</ExpressionStoT>",
            content,
        )
        if not sto_t_match:
            raise ValueError("Failed to parse <ExpressionStoT> from file")

        constant_top = float(sto_t_match.group(1))
        constant_subtract = float(sto_t_match.group(2))

        # Extract constant from ExpressionTtoS
        t_to_s_match = re.search(
            r"<ExpressionTtoS>(\d+\.\d+)/X</ExpressionTtoS>",
            content,
        )
        if not t_to_s_match:
            raise ValueError("Failed to parse <ExpressionTtoS> from file")

        constant_inverse = float(t_to_s_match.group(1))

        return BraggAngleToDistancePerpConverter(
            constant_top, constant_subtract, constant_inverse
        )


class DcmSmartLookupTable(StandardReadable):
    """
    just init with filename
    later just call
    later add new observations
    later save
    """

    def __init__(self, path: Path, settings: LookupTableSettings | None = None):
        self._settings = settings or LookupTableSettings()
        self._path = path
        self._dataframe: pd.DataFrame | None = None
        self._fit_params: np.ndarray | None = None

    def load(self, skip_lines: int = 2):
        """
        Load 2-colummn x,y Ascii data from file and convert to numbers
        (optionally skipping the first few lines)

        :param filename:
        :param lines_to_skip how many lines to skip before storing the data
        :return: dictionary containing the value on each line { x1:y1, x2:y2 ...}

        """
        print(f"Loading lookup table from {self._path}")
        self._dataframe = pd.read_csv(
            self._path,
            sep=" ",
            skiprows=skip_lines,
            names=self._settings.column_names,
        )
        self._dataframe.info()

    def fit(self, **kwargs) -> None:
        """
        Load undulator gap lookup table from Ascii file
        and fit quadratic curve to undlator gap vs Bragg angle

        :param filename:
        :param kwargs:
        :return: function that returns the best undulator gap value for a given Bragg angle
        """
        if self._dataframe is None:
            raise ValueError("Dataframe not loaded")
        data_dict = dict(
            zip(self._dataframe.iloc[:, 0], self._dataframe.iloc[:, 1], strict=False)
        )
        self._fit_params, _ = fit_quadratic_curve(data_dict, **kwargs)

    def interpolate(self, bragg_angle: float) -> float:
        if self._fit_params is None:
            raise ValueError("Fit parameters not computed")
        return quadratic(bragg_angle, *self._fit_params)

    def save_fit_results(self, filename: Path):
        """
        Save results from running
        :py:func:`spectroscopy_bluesky.i18.plans.undulator_lookuptable_scan`
        plan to Ascii file
        The top of the file contains :
        <li> Two lines of header showing fit parameters (if fit_params is set)
        <li> One header line showing the column names ('Bragg' and 'ID gap')
        <li> Two columns of data : bragg angle and undulator gap

        :param filename:
        :param bragg_angles: list of bragg angles
        :param gap_values: list of undulator gap values
        :param fit_params: optional fit parameters
        (quadratic fit to the bragg angle - undulator gap profile)
        """
        if self._dataframe is None:
            raise ValueError("Dataframe not loaded")

        with open(filename, "w") as f:
            if self._fit_params is not None:
                json_string = json.dumps(self._fit_params.tolist())
                f.write(
                    "# Quadratic fit parameters (x = Bragg, gap = a + b*x + c*x*x)\n"
                    f"# {json_string}\n"
                )
            self._dataframe.to_csv(f, **self._settings.model_dump())

    def dump_model(self, bragg_start: float, bragg_end: float, bragg_step: float):
        if self._fit_params is None:
            raise ValueError("Fit parameters not available")

        step = abs(bragg_step)
        if bragg_start > bragg_end:
            step = -1 * step
        bragg_vals = np.arange(bragg_start, bragg_end + bragg_step, step).tolist()
        bragg_vals.append(bragg_end)
        gap_vals = [quadratic(v, *self._fit_params) for v in bragg_vals]

        dataframe = pd.DataFrame(
            {
                self._settings.column_names[0]: bragg_vals,
                self._settings.column_names[1]: gap_vals,
            }
        )

        with open(self._path, "w") as f:
            f.write("# bragg    idgap\n")
            dataframe.to_csv(
                f, header=["Units", "Deg mm"], **self._settings.model_dump()
            )

    @staticmethod
    def load_fit_results(filename: Path) -> tuple[pd.DataFrame, np.ndarray | None]:
        dataframe = pd.read_csv(
            filename,
            comment="#",
            sep=r"\s+",
            header=None,
            names=LookupTableSettings().column_names,
        )
        fit_params = None
        with open(filename) as f:
            if "Quadratic" in f.readline():
                fit_params_string = f.readline().replace("#", "")
                fit_params = np.array(json.loads(fit_params_string))

        return dataframe, fit_params

    @staticmethod
    def lookup_value(
        y_search,
        func: Callable[[float], float],
        range_min=0,
        range_max=100,
        tolerance=1e-6,
        max_iters=20,
    ):
        """
        Lookup x value for a curve y(x), such that y_search = y(x)
        Uses interval bisection to reach desired accuracy tolerance,
        up to maxiumum number of iterations

        """

        def eval_func(x_pos):
            return x_pos, func(x_pos)

        def in_range(v, v1, v2):
            return min(v1, v2) < v < max(v1, v2)

        lower = eval_func(range_min)
        upper = eval_func(range_max)

        iter_num = 0
        best_y = y_search + 100

        while iter_num < max_iters and math.fabs(best_y - y_search) > tolerance:
            mid = eval_func((lower[0] + upper[0]) / 2.0)
            if in_range(y_search, lower[1], mid[1]):
                upper = mid
            else:
                lower = mid
            best_y = (lower[1] + upper[1]) / 2.0
            iter_num += 1

        return (lower[0] + upper[0]) / 2.0


if __name__ == "__main__":
    ## Test evaluator
    config_root = "/scratch/gda/9.master-6March-test-newconfig/workspace_git/gda-diamond.git/configurations/i18-config"  # noqa: E501
    filename = f"{config_root}/lookupTables/Si111/Deg_dcm_perp_mm_converter.xml"
    # filename = "lookuptable_harmonic1.txt"
    # beamline_lookuptable_dir = "/dls_sw/i18/software/gda_versions/gda_9_36/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/"  # noqa: E501
    # filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic9.txt"
    # filename = "/tmp/fits.txt"
    # dataframe = load_fit_results(filename)

    # print(dataframe)
    converter = BraggAngleToDistancePerpConverter.create_from_file(filename)
    for angle in range(10, 20):
        distance = converter.bragg_angle_degrees_to_distance(angle)
        print(f"for angle {angle} there is distance: {distance}")

    # /scratch/gda/9.master-6March-test-newconfig/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/Si111/Deg_dcm_perp_mm_converter.xml  # noqa: E501
    # <JEPQuantityConverter>
    # <ExpressionStoT>12.82991823/cos(X/(180/(4.0*atan(1.0))))-0.33493688</ExpressionStoT>
    # <ExpressionTtoS>12.489/X</ExpressionTtoS>
    # <AcceptableSourceUnits>Deg</AcceptableSourceUnits>
    # <AcceptableTargetUnits>mm</AcceptableTargetUnits>
    # <SourceMinIsTargetMax>false</SourceMinIsTargetMax>
    # </JEPQuantityConverter>
