import base64
import os
from datetime import datetime
from io import BytesIO, StringIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class HarmonicData(BaseModel):
    harmonic: int
    x: list[float]
    y: list[float]


class AllHarmonics(BaseModel):
    harmonics: list[HarmonicData]


def generate_gaussian_data(
    x_offset, n_points=100, amplitude=10, center=50, width=10, noise_level=1
):
    x = np.linspace(0, 99, n_points) + x_offset
    y = amplitude * np.exp(-((x - (center + x_offset)) ** 2) / (2 * width**2))
    y += np.random.normal(0, noise_level, n_points)
    return x, y


def dataframe_to_base64_csv(df: pd.DataFrame) -> str:
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def debug_dataframe(df: pd.DataFrame, name="DataFrame") -> str:
    output = []
    output.append(f"--- {name} diagnostics ---")
    output.append(f"Shape: {df.shape}")
    output.append(f"Columns: {df.columns.tolist()}")
    output.append("Dtypes:")
    output.append(str(df.dtypes))
    output.append("Head:")
    output.append(str(df.head()))
    buffer = StringIO()
    df.info(buf=buffer)
    output.append("Info:")
    output.append(buffer.getvalue())
    output.append("-" * 40)
    return "\n".join(output)


def main():
    out_dir = "mock_gaussian_data"
    os.makedirs(out_dir, exist_ok=True)
    harmonics_list = []
    all_dfs = []
    output_txt_path = os.path.join(out_dir, "output.txt")
    with open(output_txt_path, "w") as output_txt:
        output_txt.write(f"Timestamp: {datetime.now().isoformat()}\n")
        for i in range(10):
            x_offset = i * 5
            x, y = generate_gaussian_data(x_offset)
            df = pd.DataFrame({"x": x, "y": y, "harmonic": i})
            all_dfs.append(df)
            # Save CSV
            csv_path = os.path.join(out_dir, f"gaussian_{i:02d}.csv")
            df.to_csv(csv_path, index=False)
            # Save plot
            img_path = os.path.join(out_dir, f"gaussian_{i:02d}.png")
            plt.figure()
            plt.plot(df["x"], df["y"], "o-", label=f"Offset {x_offset}")
            plt.title(f"Gaussian Dataset {i} (Offset {x_offset})")
            plt.xlabel("x")
            plt.ylabel("y")
            plt.legend()
            plt.tight_layout()
            plt.savefig(img_path)
            plt.close()
            # Pydantic harmonic
            harmonics_list.append(HarmonicData(harmonic=i, x=x.tolist(), y=y.tolist()))
            # Debug output
            dbg = debug_dataframe(df, name=f"Harmonic {i}")
            output_txt.write(dbg + "\n")
        # Combine all into a big dataframe (3rd dim = harmonics)
        big_df = pd.concat(all_dfs, ignore_index=True)
        dbg_big = debug_dataframe(big_df, name="All Harmonics Combined")
        output_txt.write(dbg_big + "\n")
        # Save base64 version of big dataframe
        base64_csv = dataframe_to_base64_csv(big_df)
        b64_path = os.path.join(out_dir, "all_harmonics_base64.txt")
        with open(b64_path, "w") as b64file:
            b64file.write(base64_csv)
        output_txt.write(f"Base64 CSV written to: {b64_path}\n")
        # Pydantic model for all harmonics
        all_harmonics = AllHarmonics(harmonics=harmonics_list)
        json_path = os.path.join(out_dir, "all_harmonics.json")
        with open(json_path, "w") as jsonfile:
            jsonfile.write(all_harmonics.model_dump_json(indent=2))
        output_txt.write(f"Pydantic JSON written to: {json_path}\n")
    print(
        f"Generated 10 mock gaussian CSVs, PNGs, base64, and debug info in '{out_dir}'"
    )


if __name__ == "__main__":
    main()
