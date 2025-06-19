import base64
from io import BytesIO

import pandas as pd
from pydantic import BaseModel


class BraggAngleData(BaseModel):
    bragg_angle_x: float
    gap_x_2: list[float]
    diode_y: list[float]


class HarmonicData(BaseModel):
    harmonic: int
    bragg_angles: list[BraggAngleData]


class AllHarmonics(BaseModel):
    harmonics: list[HarmonicData]


def dataframe_to_base64_csv(df: pd.DataFrame) -> str:
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
