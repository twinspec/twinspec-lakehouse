# scripts/digitize_giwaxs.py

import csv
import json
from pathlib import Path
from datetime import datetime


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_LIT = REPO_ROOT / "raw" / "literature"
GIWAXS_1D_DIR = RAW_LIT / "giwaxs_1d"
GIWAXS_2D_DIR = RAW_LIT / "giwaxs_2d"


def standardize_1d_linecut(
    raw_csv_path: Path,
    experiment_id: str,
    linecut_id: str,
    direction: str,
    q_units: str,
    intensity_units: str = "arb",
) -> Path:
    """
    Convert a raw 1D linecut CSV (e.g. from WebPlotDigitizer) into
    a standardized format used by TwinSpec.

    Output schema:
        experiment_id,linecut_id,direction,q_units,intensity_units,q,intensity
    """
    raw_csv_path = raw_csv_path.expanduser().resolve()
    GIWAXS_1D_DIR.mkdir(parents=True, exist_ok=True)

    out_name = f"{experiment_id}_{linecut_id}.csv"
    out_path = GIWAXS_1D_DIR / out_name

    # naive: assume first two columns are x,y (q,intensity)
    with raw_csv_path.open("r", newline="") as f_in, out_path.open("w", newline="") as f_out:
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)

        # try to skip header row if it's non-numeric
        first_row = next(reader)
        try:
            float(first_row[0])
            # header is numeric; use it as data
            data_rows = [first_row] + list(reader)
        except ValueError:
            # header is text; skip and use the rest
            data_rows = list(reader)

        writer.writerow(
            [
                "experiment_id",
                "linecut_id",
                "direction",
                "q_units",
                "intensity_units",
                "q",
                "intensity",
            ]
        )

        for row in data_rows:
            if not row or len(row) < 2:
                continue
            q_val = row[0]
            I_val = row[1]
            writer.writerow(
                [
                    experiment_id,
                    linecut_id,
                    direction,
                    q_units,
                    intensity_units,
                    q_val,
                    I_val,
                ]
            )

    print(f"[1D] wrote standardized linecut to: {out_path.relative_to(REPO_ROOT)}")
    return out_path


def standardize_2d_map(
    raw_csv_path: Path,
    experiment_id: str,
    map_id: str,
    geometry: str,
    qz_units: str,
    qxy_units: str,
) -> Path:
    """
    Convert a raw 2D GIWAXS map CSV into TwinSpec standard long-form:

        experiment_id,map_id,geometry,qz_units,qxy_units,qz,qxy,intensity
    """
    raw_csv_path = raw_csv_path.expanduser().resolve()
    GIWAXS_2D_DIR.mkdir(parents=True, exist_ok=True)

    out_name = f"{experiment_id}_{map_id}.csv"
    out_path = GIWAXS_2D_DIR / out_name

    with raw_csv_path.open("r", newline="") as f_in, out_path.open("w", newline="") as f_out:
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)

        first_row = next(reader)
        # Assume long-form: qz,qxy,intensity
        try:
            float(first_row[0])
            data_rows = [first_row] + list(reader)
        except ValueError:
            data_rows = list(reader)

        writer.writerow(
            [
                "experiment_id",
                "map_id",
                "geometry",
                "qz_units",
                "qxy_units",
                "qz",
                "qxy",
                "intensity",
            ]
        )

        for row in data_rows:
            if not row or len(row) < 3:
                continue
            qz, qxy, I = row[0], row[1], row[2]
            writer.writerow(
                [
                    experiment_id,
                    map_id,
                    geometry,
                    qz_units,
                    qxy_units,
                    qz,
                    qxy,
                    I,
                ]
            )

    print(f"[2D] wrote standardized map to: {out_path.relative_to(REPO_ROOT)}")
    return out_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Standardize GIWAXS digitized CSV files into TwinSpec formats."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # 1D
    p1d = subparsers.add_parser("1d", help="Process a 1D linecut CSV")
    p1d.add_argument("--raw", required=True, help="Path to raw CSV from digitizer")
    p1d.add_argument("--experiment-id", required=True)
    p1d.add_argument(
        "--linecut-id",
        required=False,
        default="linecut",
        help="Short label, e.g. oop, ip, radial",
    )
    p1d.add_argument(
        "--direction",
        required=False,
        default="out_of_plane",
        help="out_of_plane, in_plane, radial, azimuthal, sector, etc.",
    )
    p1d.add_argument("--q-units", required=False, default="1/A")
    p1d.add_argument("--intensity-units", required=False, default="arb")

    # 2D
    p2d = subparsers.add_parser("2d", help="Process a 2D map CSV")
    p2d.add_argument("--raw", required=True, help="Path to raw CSV from digitizer")
    p2d.add_argument("--experiment-id", required=True)
    p2d.add_argument(
        "--map-id",
        required=False,
        default="map",
        help="Short id for this map, e.g. full, masked, etc.",
    )
    p2d.add_argument(
        "--geometry",
        required=False,
        default="qz_qxy",
        help="qz_qxy, qx_qy, detector_pixels, etc.",
    )
    p2d.add_argument("--qz-units", required=False, default="1/A")
    p2d.add_argument("--qxy-units", required=False, default="1/A")

    args = parser.parse_args()

    if args.mode == "1d":
        standardize_1d_linecut(
            Path(args.raw),
            args.experiment_id,
            args.linecut_id,
            args.direction,
            args.q_units,
            args.intensity_units,
        )
    elif args.mode == "2d":
        standardize_2d_map(
            Path(args.raw),
            args.experiment_id,
            args.map_id,
            args.geometry,
            args.qz_units,
            args.qxy_units,
        )
    else:
        parser.error("Unknown mode")


if __name__ == "__main__":
    main()