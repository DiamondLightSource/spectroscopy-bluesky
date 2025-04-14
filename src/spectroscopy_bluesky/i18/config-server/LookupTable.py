import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel

from spectroscopy_bluesky.i18.plans.curve_fitting.curve_fitting import (
    fit_quadratic_curve,
)
from spectroscopy_bluesky.i18.plans.curve_fitting.stats import quadratic


class LookupTableSettings(BaseModel):
    float_format: str = "%9.5f"
    sep: str = "\t"
    index: bool | None = None
    column_names: list[str] = ["Bragg [deg]", "ID gap [mm]"]


class LookupTable:
    def __init__(self, path: Path, settings: LookupTableSettings | None = None):
        self._settings = settings or LookupTableSettings()
        self._path = path
        self._dataframe: pd.DataFrame | None = None
        self._fit_params: np.ndarray | None = None

    def load(self, skip_lines: int = 2):
        print(f"Loading lookup table from {self._path}")
        self._dataframe = pd.read_csv(
            self._path,
            sep=" ",
            skiprows=skip_lines,
            names=self._settings.column_names,
        )
        self._dataframe.info()

    def as_dict(self) -> dict:
        if self._dataframe is None:
            raise ValueError("Dataframe not loaded")
        return dict(
            zip(self._dataframe.iloc[:, 0], self._dataframe.iloc[:, 1], strict=False)
        )

    def fit(self, **kwargs) -> None:
        if self._dataframe is None:
            raise ValueError("Dataframe not loaded")
        data_dict = self.as_dict()
        self._fit_params, _ = fit_quadratic_curve(data_dict, **kwargs)

    def interpolate(self, bragg_angle: float) -> float:
        if self._fit_params is None:
            raise ValueError("Fit parameters not computed")
        return quadratic(bragg_angle, *self._fit_params)

    def save_fit_results(self, filename: Path):
        if self._dataframe is None:
            raise ValueError("Dataframe not loaded")

        with open(filename, "w") as f:
            if self._fit_params is not None:
                json_string = json.dumps(self._fit_params.tolist())
                f.write(
                    "# Quadratic fit parameters (x = Bragg, gap = a + b*x + c*x*x)\n"
                    f"# {json_string}\n"
                )
            self._dataframe.to_csv(f, **self._settings.dict())

    def generate_ascii_lookup(
        self, filename: Path, bragg_start: float, bragg_end: float, bragg_step: float
    ):
        if self._fit_params is None:
            raise ValueError("Fit parameters not available")

        step = abs(bragg_step) if bragg_start < bragg_end else -abs(bragg_step)
        bragg_vals = np.arange(bragg_start, bragg_end + bragg_step, step).tolist()
        bragg_vals.append(bragg_end)
        gap_vals = [quadratic(v, *self._fit_params) for v in bragg_vals]

        dataframe = pd.DataFrame(
            {
                self._settings.column_names[0]: bragg_vals,
                self._settings.column_names[1]: gap_vals,
            }
        )

        with open(filename, "w") as f:
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
        y_search, func, range_min=0, range_max=100, tolerance=1e-6, max_iters=20
    ):
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
