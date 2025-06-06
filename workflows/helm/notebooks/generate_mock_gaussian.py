import base64
import os
from datetime import datetime
from io import BytesIO, StringIO

import matplotlib.pyplot as plt
import numpy as np
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


def generate_gaussian_data(
    bragg_angle, n_points=100, amplitude=10, center=50, width=10, noise_level=1
):
    x = np.linspace(0, 99, n_points)
    y = amplitude * np.exp(-((x - center) ** 2) / (2 * width**2))
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


def plot_gaussian(df: pd.DataFrame, img_path: str, label: str):
    plt.figure()
    plt.plot(df["x"], df["y"], "o-", label=label)
    plt.title(label)
    plt.xlabel("x")
    plt.ylabel("y")
    plt.legend()
    plt.tight_layout()
    plt.savefig(img_path)
    plt.close()


def main():
    out_dir = "mock_gaussian_data"
    os.makedirs(out_dir, exist_ok=True)
    harmonics_list = []
    output_txt_path = os.path.join(out_dir, "output.txt")
    with open(output_txt_path, "w") as output_txt:
        output_txt.write(f"Timestamp: {datetime.now().isoformat()}\n")
        for harmonic in range(3):  # Example: 3 harmonics
            harmonic_dir = os.path.join(out_dir, f"harmonic_{harmonic}")
            os.makedirs(harmonic_dir, exist_ok=True)
            bragg_angle_list = []
            all_dfs = []
            for i, bragg_angle in enumerate(np.linspace(10, 60, 10)):  # 10 Bragg angles
                x, y = generate_gaussian_data(bragg_angle)
                df = pd.DataFrame({"x": x, "y": y, "bragg_angle": bragg_angle})
                all_dfs.append(df)
                # Save CSV
                csv_path = os.path.join(harmonic_dir, f"bragg_{i:02d}.csv")
                df.to_csv(csv_path, index=False)
                # Save base64-encoded CSV
                b64_csv = dataframe_to_base64_csv(df)
                b64_csv_path = os.path.join(harmonic_dir, f"bragg_{i:02d}_base64.txt")
                with open(b64_csv_path, "w") as b64file:
                    b64file.write(b64_csv)
                # Save plot
                img_path = os.path.join(harmonic_dir, f"bragg_{i:02d}.png")
                plot_gaussian(
                    df, img_path, label=f"Harmonic {harmonic}, Bragg {bragg_angle:.2f}"
                )
                # Pydantic BraggAngleData
                bragg_angle_list.append(
                    BraggAngleData(
                        bragg_angle_x=bragg_angle,
                        gap_x_2=x.tolist(),
                        diode_y=y.tolist(),
                    )
                )
                # Debug output
                dbg = debug_dataframe(
                    df, name=f"Harmonic {harmonic} Bragg {bragg_angle:.2f}"
                )
                output_txt.write(dbg + "\n")
            # Combine all Bragg angle dataframes for this harmonic
            big_df = pd.concat(all_dfs, ignore_index=True)
            dbg_big = debug_dataframe(
                big_df, name=f"Harmonic {harmonic} All Bragg Angles Combined"
            )
            output_txt.write(dbg_big + "\n")
            # Save base64 version of big dataframe
            base64_csv = dataframe_to_base64_csv(big_df)
            b64_path = os.path.join(harmonic_dir, "all_bragg_angles_base64.txt")
            with open(b64_path, "w") as b64file:
                b64file.write(base64_csv)
            output_txt.write(f"Base64 CSV written to: {b64_path}\n")
            # Pydantic HarmonicData
            harmonics_list.append(
                HarmonicData(harmonic=harmonic, bragg_angles=bragg_angle_list)
            )
        # Save all harmonics as JSON
        all_harmonics = AllHarmonics(harmonics=harmonics_list)
        json_path = os.path.join(out_dir, "all_harmonics.json")
        with open(json_path, "w") as jsonfile:
            jsonfile.write(all_harmonics.model_dump_json(indent=2))
        output_txt.write(f"Pydantic JSON written to: {json_path}\n")
    print(f"Generated mock gaussian data for harmonics and Bragg angles in '{out_dir}'")


if __name__ == "__main__":
    main()
