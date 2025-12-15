import argparse
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def extract_core_columns(
    input_csv: Path,
    output_csv: Path,
):
    input_csv = input_csv.expanduser().resolve()
    output_csv = output_csv.expanduser().resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", newline="", encoding="utf-8") as f_in, \
         output_csv.open("w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)

        # Core numeric schema
        writer.writerow(["qz", "qxy", "intensity"])

        for row in reader:
            qz = row["qz"]
            qxy = row["qxy"]
            intensity = row["intensity"]

            # Skip empty or NaN intensity rows
            if intensity == "" or intensity.lower() == "nan":
                continue

            writer.writerow([qz, qxy, intensity])

    print(f"[extract] wrote core GIWAXS CSV to: {output_csv.relative_to(REPO_ROOT)}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract qz, qxy, intensity columns from TwinSpec GIWAXS CSV"
    )
    parser.add_argument("--input", required=True, help="Path to digitized GIWAXS CSV")
    parser.add_argument("--output", required=True, help="Path to output core CSV")
    args = parser.parse_args()

    extract_core_columns(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()