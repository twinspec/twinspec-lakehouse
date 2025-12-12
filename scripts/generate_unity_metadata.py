import csv
import json
from pathlib import Path
from typing import Dict, Any

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPERIMENTS_CSV = REPO_ROOT / "curated" / "experiments" / "experiments.csv"
MATERIALS_CSV = REPO_ROOT / "curated" / "materials" / "materials.csv"
OUTPUT_DIR = REPO_ROOT / "unity_metadata"


def load_material_names() -> Dict[str, Dict[str, str]]:
    """Return dict material_id -> {name, class, subclass}."""
    mapping: Dict[str, Dict[str, str]] = {}
    if not MATERIALS_CSV.exists():
        print(f"[WARN] materials.csv not found at {MATERIALS_CSV}, continuing without names.")
        return mapping

    with MATERIALS_CSV.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mid = row.get("material_id")
            if not mid:
                continue
            mapping[mid] = {
                "name": row.get("name", ""),
                "class": row.get("class", ""),
                "subclass": row.get("subclass", ""),
            }
    return mapping


def parse_json_field(text: str) -> Any:
    """Parse a JSON string field from CSV; return {} or None on empty/invalid."""
    if text is None:
        return {}
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"[WARN] Could not parse JSON field: {text[:80]}...")
        return {}


def truthy(val: str) -> bool:
    if val is None:
        return False
    return val.strip().lower() in {"1", "true", "yes", "y"}


def generate_unity_metadata():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    material_info = load_material_names()

    if not EXPERIMENTS_CSV.exists():
        raise SystemExit(f"experiments.csv not found at {EXPERIMENTS_CSV}")

    with EXPERIMENTS_CSV.open("r", newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            if not truthy(row.get("include_in_unity", "")):
                continue

            experiment_id = row.get("experiment_id")
            material_id = row.get("material_id")

            if not experiment_id or not material_id:
                print(f"[WARN] Skipping row with missing experiment_id/material_id: {row}")
                continue

            mat = material_info.get(material_id, {})
            material_name = mat.get("name", "")
            material_class = mat.get("class", "")
            material_subclass = mat.get("subclass", "")

            # Parse JSON-ish fields
            char_metadata = parse_json_field(row.get("char_metadata_json", ""))
            peaks = parse_json_field(row.get("peaks_json", ""))

            # Build metadata object for Unity
            meta = {
                "experiment_id": experiment_id,
                "material_id": material_id,
                "material_name": material_name,
                "material_class": material_class,
                "material_subclass": material_subclass,
                "source": {
                    "type": row.get("source_type", ""),
                    "doi": row.get("source_doi", ""),
                },
                "processing": {
                    "solvent": row.get("solvent", ""),
                    "concentration_mg_ml": _maybe_float(row.get("concentration_mg_ml")),
                    "casting_method": row.get("casting_method", ""),
                    "substrate": row.get("substrate", ""),
                    "anneal_temp_C": _maybe_float(row.get("anneal_temp_C")),
                    "anneal_time_min": _maybe_float(row.get("anneal_time_min")),
                    "film_thickness_nm": _maybe_float(row.get("film_thickness_nm")),
                },
                "characterization": {
                    "char_type": row.get("char_type", ""),
                    "metadata": char_metadata,
                    "peaks": peaks,
                    "orientation_label": row.get("orientation_label", ""),
                },
                "paths": {
                    # repository-relative; Unity can map these however you like
                    "giwaxs_1d_csv": row.get("giwaxs_1d_path", ""),
                    "giwaxs_2d_csv": row.get("giwaxs_2d_path", ""),
                    # you can add an image path convention later:
                    # "giwaxs_image_2d": f"giwaxs/{experiment_id}.png"
                },
                "notes": row.get("notes", ""),
            }

            out_path = OUTPUT_DIR / f"{experiment_id}.json"
            with out_path.open("w") as f_out:
                json.dump(meta, f_out, indent=2)

            print(f"[OK] Wrote Unity metadata: {out_path.relative_to(REPO_ROOT)}")
            count += 1

    print(f"\nDone. Generated {count} Unity metadata file(s).")


def _maybe_float(val: str):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return s  # leave as string if not numeric


if __name__ == "__main__":
    generate_unity_metadata()