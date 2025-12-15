import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_LIT = REPO_ROOT / "raw" / "literature"
GIWAXS_2D_DIR = RAW_LIT / "giwaxs_2d_csv"


def rgb_to_intensity(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1].astype(np.float32)
    b = rgb[..., 2].astype(np.float32)
    return 0.299 * r + 0.587 * g + 0.114 * b


def digitize_giwaxs_image(
    image_path: Path,
    experiment_id: str,
    map_id: str,
    qz_min: float,
    qz_max: float,
    qxy_min: float,
    qxy_max: float,
    q_units: str = "1/nm",
    geometry: str = "qz_qxy",
    downsample: int = 1,
    ignore_rgb: tuple[int, int, int] | None = (0, 0, 0),
    ignore_border_px: int = 0,
    missing_wedge_fill_strategy: str = "skip",  # "skip" or "nan"
    out_path: Path | None = None,
) -> Path:
    image_path = image_path.expanduser().resolve()
    GIWAXS_2D_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)  # (H, W, 3)

    H, W, _ = arr.shape

    # Optional border ignore (helps remove residual labels/frames)
    if ignore_border_px and ignore_border_px > 0:
        b = int(ignore_border_px)
        if 2 * b >= H or 2 * b >= W:
            raise ValueError(f"ignore_border_px={b} too large for image size {(H, W)}")
        arr = arr[b:H - b, b:W - b, :]
        H, W, _ = arr.shape

    crop = arr
    Hc, Wc, _ = crop.shape

    # Mask pixels by exact RGB (default: pure black)
    if ignore_rgb is not None:
        r0, g0, b0 = ignore_rgb
        mask = (crop[..., 0] == r0) & (crop[..., 1] == g0) & (crop[..., 2] == b0)
    else:
        mask = np.zeros((Hc, Wc), dtype=bool)

    intensity = rgb_to_intensity(crop)

    # Build coordinate grids
    y = np.arange(Hc)
    x = np.arange(Wc)

    # qz: bottom -> qz_min, top -> qz_max
    if Hc == 1:
        qz_grid = np.full((Hc, Wc), qz_min, dtype=np.float32)
    else:
        qz_grid = qz_min + (Hc - 1 - y[:, None]) / (Hc - 1) * (qz_max - qz_min)

    # qxy: left -> qxy_min, right -> qxy_max
    if Wc == 1:
        qxy_grid = np.full((Hc, Wc), qxy_min, dtype=np.float32)
    else:
        qxy_grid = qxy_min + x[None, :] / (Wc - 1) * (qxy_max - qxy_min)

    step = max(1, int(downsample))
    qz_ds = qz_grid[::step, ::step]
    qxy_ds = qxy_grid[::step, ::step]
    I_ds = intensity[::step, ::step]
    mask_ds = mask[::step, ::step]

    qz_flat = qz_ds.ravel()
    qxy_flat = qxy_ds.ravel()
    I_flat = I_ds.ravel()
    mask_flat = mask_ds.ravel()

    if missing_wedge_fill_strategy == "nan":
        # keep points, but set masked intensities to NaN
        I_flat = I_flat.astype(np.float32)
        I_flat[mask_flat] = np.nan
        keep = np.ones_like(mask_flat, dtype=bool)
    else:
        # default: skip masked pixels entirely
        keep = ~mask_flat

    qz_flat = qz_flat[keep]
    qxy_flat = qxy_flat[keep]
    I_flat = I_flat[keep]

    if out_path is None:
        out_name = f"{experiment_id}_{map_id}.csv"
        out_path = GIWAXS_2D_DIR / out_name
    else:
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["experiment_id", "map_id", "geometry", "qz_units", "qxy_units", "qz", "qxy", "intensity"])
        for qz_val, qxy_val, I_val in zip(qz_flat, qxy_flat, I_flat):
            # write NaN cleanly if present
            I_str = "" if (isinstance(I_val, float) and np.isnan(I_val)) else f"{float(I_val):.6g}"
            w.writerow([experiment_id, map_id, geometry, q_units, q_units, f"{float(qz_val):.6g}", f"{float(qxy_val):.6g}", I_str])

    print(f"[2D image] wrote digitized GIWAXS map to: {out_path.relative_to(REPO_ROOT)}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Digitize GIWAXS 2D image using characterization_metadata.json")
    parser.add_argument("--characterization-json", required=True, help="Path to characterization metadata JSON")
    parser.add_argument("--no-ignore-black", action="store_true", help="Disable masking of pure black pixels")
    args = parser.parse_args()

    meta_path = Path(args.characterization_json).expanduser().resolve()
    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    experiment_id = meta["experiment_id"]
    characterization_id = meta.get("characterization_id", "")
    map_id = meta.get("role", "2d_map")  # role is your stable semantic ID

    # Prefer post-crop path if present, else raw crop path
    image_path = meta.get("image_processing", {}).get("post_crop_path") or meta.get("raw_inputs", {}).get("source_figure_crop_path")
    if not image_path:
        raise ValueError("No image path found in characterization metadata (post_crop_path or source_figure_crop_path).")

    qmap = meta.get("q_mapping", {})
    qz_min = float(qmap["qz_min"])
    qz_max = float(qmap["qz_max"])
    qxy_min = float(qmap["qxy_min"])
    qxy_max = float(qmap["qxy_max"])
    q_units = qmap.get("units", "1/nm")
    geometry = qmap.get("geometry", "qz_qxy")

    downsample = int(meta.get("image_processing", {}).get("downsample_factor") or 1)

    dig_params = meta.get("digitization", {}).get("parameters", {})
    ignore_border_px = int(dig_params.get("ignore_border_px") or 0)
    missing_wedge_fill_strategy = dig_params.get("missing_wedge_fill_strategy", "skip")

    ignore_rgb = None if args.no_ignore_black else (0, 0, 0)

    # Output path: if JSON already specifies it, use that; else default convention.
    out_spec = meta.get("digitization", {}).get("outputs", {}).get("digitized_2d_csv_path", "")
    if out_spec:
        out_path = REPO_ROOT / out_spec
    else:
        out_path = GIWAXS_2D_DIR / f"{experiment_id}_{map_id}.csv"

    out_path = digitize_giwaxs_image(
        image_path=REPO_ROOT / image_path,
        experiment_id=experiment_id,
        map_id=map_id,
        qz_min=qz_min,
        qz_max=qz_max,
        qxy_min=qxy_min,
        qxy_max=qxy_max,
        q_units=q_units,
        geometry=geometry,
        downsample=downsample,
        ignore_rgb=ignore_rgb,
        ignore_border_px=ignore_border_px,
        missing_wedge_fill_strategy=missing_wedge_fill_strategy,
        out_path=out_path,
    )

    # Write back into metadata JSON (relative path)
    rel_out = out_path.relative_to(REPO_ROOT).as_posix()
    meta.setdefault("digitization", {}).setdefault("outputs", {})["digitized_2d_csv_path"] = rel_out

    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"[meta] updated digitized_2d_csv_path in: {meta_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
