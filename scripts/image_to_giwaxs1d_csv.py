import argparse
import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image
from matplotlib.colors import rgb_to_hsv

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_LIT = REPO_ROOT / "raw" / "literature"
GIWAXS_1D_DIR = RAW_LIT / "giwaxs_1d_csv"


def _pixel_to_q(x: np.ndarray, W: int, q_min: float, q_max: float) -> np.ndarray:
    if W <= 1:
        return np.full_like(x, q_min, dtype=np.float32)
    frac = x / (W - 1)
    return q_min + frac * (q_max - q_min)


def _pixel_to_intensity(
    y: np.ndarray,
    H: int,
    I_min: float,
    I_max: float,
    scale: str,
) -> np.ndarray:
    """
    y is pixel row (0 at top). Intensity axis increases upward.
    """
    if H <= 1:
        frac = np.zeros_like(y, dtype=np.float32)
    else:
        frac = (H - 1 - y) / (H - 1)  # bottom->0, top->1

    if scale.lower() == "log10":
        if I_min <= 0 or I_max <= 0:
            raise ValueError(f"log10 intensity scale requires positive I_min/I_max, got {I_min}, {I_max}")
        lo = np.log10(I_min)
        hi = np.log10(I_max)
        return np.power(10.0, lo + frac * (hi - lo)).astype(np.float32)

    # linear
    return (I_min + frac * (I_max - I_min)).astype(np.float32)


def _blue_mask(
    rgb_u8: np.ndarray,
    h_min: float = 0.52,
    h_max: float = 0.78,
    s_min: float = 0.20,
    v_min: float = 0.10,
) -> np.ndarray:
    """
    Heuristic mask for "blue-ish" curve pixels.
    hsv hue range defaults catch navy->light-blue.
    """
    rgb = rgb_u8.astype(np.float32) / 255.0
    hsv = rgb_to_hsv(rgb)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (h >= h_min) & (h <= h_max) & (s >= s_min) & (v >= v_min)


def _column_candidates(mask: np.ndarray) -> list[list[float]]:
    """
    For each x column, return candidate y positions (one per detected curve segment).
    We find contiguous True runs in y and take the mean y of each run.
    """
    H, W = mask.shape
    cands_per_x: list[list[float]] = []
    for x in range(W):
        ys = np.where(mask[:, x])[0]
        if ys.size == 0:
            cands_per_x.append([])
            continue

        # split into contiguous runs
        runs = []
        start = ys[0]
        prev = ys[0]
        for y in ys[1:]:
            if y == prev + 1:
                prev = y
            else:
                runs.append((start, prev))
                start = y
                prev = y
        runs.append((start, prev))

        # representative y for each run
        reps = [0.5 * (a + b) for (a, b) in runs]
        cands_per_x.append(reps)

    return cands_per_x


def _initialize_tracks(cands_per_x: list[list[float]], num_curves: int) -> tuple[int, list[float]]:
    """
    Find the first x where we have at least num_curves candidates.
    Initialize tracks by sorted y (top->bottom order).
    """
    for x0, reps in enumerate(cands_per_x):
        if len(reps) >= num_curves:
            reps_sorted = sorted(reps)[:num_curves]
            return x0, reps_sorted
    raise ValueError(f"Could not find a column with >= {num_curves} curve candidates.")


def _track_curves(cands_per_x: list[list[float]], num_curves: int, max_jump_px: float = 12.0) -> np.ndarray:
    """
    Track curves across x. Output shape (num_curves, W) with NaNs where missing.
    Greedy nearest-neighbor assignment with continuity; assumes curves don't cross.
    """
    W = len(cands_per_x)
    tracks = np.full((num_curves, W), np.nan, dtype=np.float32)

    x0, ys0 = _initialize_tracks(cands_per_x, num_curves)
    tracks[:, x0] = np.array(ys0, dtype=np.float32)

    prev = tracks[:, x0].copy()

    for x in range(x0 + 1, W):
        reps = cands_per_x[x]
        if not reps:
            continue

        reps = sorted(reps)
        used = np.zeros(len(reps), dtype=bool)
        new = prev.copy()

        # assign each track in order (top->bottom) to closest candidate y
        for i in range(num_curves):
            py = prev[i]
            if not np.isfinite(py):
                continue

            d = np.abs(np.array(reps, dtype=np.float32) - py)
            d[used] = np.inf
            j = int(np.argmin(d))
            if np.isfinite(d[j]) and d[j] <= max_jump_px:
                new[i] = reps[j]
                used[j] = True
            else:
                new[i] = np.nan

        tracks[:, x] = new
        prev = new

    return tracks


def digitize_1d_linecuts_from_image(
    image_path: Path,
    experiment_id: str,
    characterization_id: str,
    q_min: float,
    q_max: float,
    q_units: str,
    I_min: float,
    I_max: float,
    I_scale: str,
    num_curves: int,
    curve_labels: list[str] | None,
    ignore_border_px: int = 0,
    max_jump_px: float = 12.0,
) -> list[Path]:
    image_path = image_path.expanduser().resolve()
    GIWAXS_1D_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)  # (H,W,3)

    # optional border trim
    if ignore_border_px and ignore_border_px > 0:
        b = int(ignore_border_px)
        if arr.shape[0] <= 2 * b or arr.shape[1] <= 2 * b:
            raise ValueError(f"ignore_border_px={b} too large for image size {arr.shape[:2]}")
        arr = arr[b:-b, b:-b, :]

    H, W, _ = arr.shape

    # mask curve pixels (blue-ish)
    mask = _blue_mask(arr)

    # build candidates per x, track N curves
    cands_per_x = _column_candidates(mask)
    tracks_y = _track_curves(cands_per_x, num_curves=num_curves, max_jump_px=max_jump_px)  # (N,W)

    x = np.arange(W, dtype=np.float32)
    q = _pixel_to_q(x, W, q_min, q_max)

    out_paths: list[Path] = []
    if curve_labels is None or len(curve_labels) != num_curves:
        curve_labels = [f"curve_{i+1:02d}" for i in range(num_curves)]

    for i in range(num_curves):
        y = tracks_y[i, :]
        good = np.isfinite(y)
        if not np.any(good):
            continue

        intensity = np.full_like(y, np.nan, dtype=np.float32)
        intensity[good] = _pixel_to_intensity(y[good], H, I_min, I_max, I_scale)

        linecut_id = curve_labels[i]
        out_path = GIWAXS_1D_DIR / f"{characterization_id}__{linecut_id}.csv"

        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                ["experiment_id", "characterization_id", "linecut_id", "q_units", "intensity_units", "q", "intensity"]
            )
            for qq, ii in zip(q, intensity):
                if not np.isfinite(ii):
                    continue
                w.writerow(
                    [experiment_id, characterization_id, linecut_id, q_units, "arb", f"{float(qq):.6g}", f"{float(ii):.6g}"]
                )

        out_paths.append(out_path)

    return out_paths


def _get_required_float(d: dict, keys: list[str], context: str) -> float:
    """
    Return the first present key from keys as float, else raise a helpful error.
    """
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return float(d[k])
    raise KeyError(f"Missing required field in {context}: expected one of {keys}")


def main():
    p = argparse.ArgumentParser(description="Digitize stacked GIWAXS 1D linecuts from an image using characterization JSON.")
    p.add_argument("--characterization-json", required=True)
    args = p.parse_args()

    meta_path = Path(args.characterization_json).expanduser().resolve()
    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    experiment_id = meta["experiment_id"]
    characterization_id = meta["characterization_id"]

    image_path = (
        meta.get("image_processing", {}).get("post_crop_path")
        or meta.get("raw_inputs", {}).get("source_figure_crop_path")
    )
    if not image_path:
        raise ValueError("No image path found in characterization metadata (image_processing.post_crop_path or raw_inputs.source_figure_crop_path).")

    # ---- q mapping (1D) ----
    qmap = meta.get("q_mapping", {})
    q_min = _get_required_float(qmap, ["q_min"], "q_mapping")
    q_max = _get_required_float(qmap, ["q_max"], "q_mapping")
    q_units = qmap.get("units", "1/A")

    # ---- intensity axis ----
    iax = meta.get("intensity_axis", {})

    # Backward compatible: accept either min/max or I_min/I_max
    I_min = _get_required_float(iax, ["min", "I_min"], "intensity_axis")
    I_max = _get_required_float(iax, ["max", "I_max"], "intensity_axis")
    I_scale = iax.get("scale", "log10")

    # ---- digitization params ----
    dig = meta.get("digitization", {}).get("parameters", {})
    num_curves = int(dig.get("num_curves", 1))
    curve_labels = dig.get("curve_labels", None)
    ignore_border_px = int(dig.get("ignore_border_px", 0))
    max_jump_px = float(dig.get("max_jump_px", 12.0))

    out_paths = digitize_1d_linecuts_from_image(
        image_path=REPO_ROOT / image_path,
        experiment_id=experiment_id,
        characterization_id=characterization_id,
        q_min=q_min,
        q_max=q_max,
        q_units=q_units,
        I_min=I_min,
        I_max=I_max,
        I_scale=I_scale,
        num_curves=num_curves,
        curve_labels=curve_labels,
        ignore_border_px=ignore_border_px,
        max_jump_px=max_jump_px,
    )

    # write outputs back into metadata
    outs = meta.setdefault("digitization", {}).setdefault("outputs", {})
    outs["digitized_1d_csv_paths"] = [p.relative_to(REPO_ROOT).as_posix() for p in out_paths]

    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"[1D] wrote {len(out_paths)} linecut CSVs and updated: {meta_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()