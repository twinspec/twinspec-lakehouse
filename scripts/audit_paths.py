# scripts/audit_paths.py

import csv
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPERIMENTS_CSV = REPO_ROOT / "curated" / "experiments" / "experiments.csv"
COMPUTED_STRUCTURES_CSV = REPO_ROOT / "curated" / "computed_structures" / "computed_structures.csv"


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        print(f"[WARN] CSV not found: {path}")
        return []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def check_file(path_str: str) -> bool:
    if not path_str:
        return True
    path = (REPO_ROOT / path_str).resolve()
    return path.exists()


def audit_experiments() -> List[Tuple[str, str, str]]:
    rows = read_csv(EXPERIMENTS_CSV)
    missing = []
    for row in rows:
        exp_id = row.get("experiment_id", "<unknown>")
        p1d = row.get("giwaxs_1d_path", "").strip()
        p2d = row.get("giwaxs_2d_path", "").strip()

        if p1d and not check_file(p1d):
            missing.append(("experiment", exp_id, p1d))
        if p2d and not check_file(p2d):
            missing.append(("experiment", exp_id, p2d))
    return missing


def audit_structures() -> List[Tuple[str, str, str]]:
    rows = read_csv(COMPUTED_STRUCTURES_CSV)
    missing = []
    for row in rows:
        struct_id = row.get("structure_id", "<unknown>")
        gpath = row.get("geometry_path", "").strip()
        if gpath and not check_file(gpath):
            missing.append(("structure", struct_id, gpath))
    return missing


def main():
    missing = []
    missing.extend(audit_experiments())
    missing.extend(audit_structures())

    if not missing:
        print("All referenced file paths exist.")
        return

    print("Missing files detected:")
    for kind, ident, rel in missing:
        print(f"  - {kind} {ident}: {rel} (NOT FOUND)")

    print(f"\nTotal missing: {len(missing)}")
    # Non-zero exit code is useful if you wire this into CI later.
    raise SystemExit(1)


if __name__ == "__main__":
    main()