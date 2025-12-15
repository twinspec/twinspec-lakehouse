import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_LIT = REPO_ROOT / "raw" / "literature"
GIWAXS_2D_DIR = RAW_LIT / "giwaxs_2d"


def rgb_to_intensity(rgb: np.ndarray) -> np.ndarray:
    """
    Convert RGB image to a single-channel intensity using a standard
    luminance transform.

    rgb: (H, W, 3) uint8
    returns: (H, W) float32 in [0, 255]
    """
    # Y = 0.299 R + 0.587 G + 0.114 B
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
    data_left: int | None = None,
    data_right: int | None = None,
    data_top: int | None = None,
    data_bottom: int | None = None,
    downsample: int = 1,
    ignore_rgb: tuple[int, int, int] | None = (0, 0, 0),
) -> Path:
    """
    Digitize a GIWAXS 2D pattern image into a long-form CSV.

    Assumptions:
      - Image is roughly cropped so that the GIWAXS map is axis-aligned
        (qxy horizontally, qz vertically).
      - qz increases from bottom to top of the data region.
      - qxy increases from left to right.
      - Any pixels with RGB == ignore_rgb are treated as "no data" and skipped
        (e.g. painted-black color bars, labels, wedges).

    Parameters
    ----------
    image_path : Path
        Path to PNG/JPEG image.
    experiment_id : str
    map_id : str
    qz_min, qz_max : float
        Axis limits in physical units (e.g. 0, 17).
    qxy_min, qxy_max : float
        Axis limits in physical units.
    q_units : str
        Units string for both qz and qxy (e.g. "1/nm", "1/A").
    geometry : str
        Label describing coordinate system (default "qz_qxy").
    data_left, data_right, data_top, data_bottom : int or None
        Pixel bounds of the data region. If None, use full image.
        (left/right are x indices, top/bottom are y indices).
    downsample : int
        Step size in pixels for subsampling (1 = use every pixel).
    ignore_rgb : tuple or None
        Exact RGB color to treat as masked (default black).
        Set to None to disable masking by color.

    Returns
    -------
    Path to the output CSV inside raw/literature/giwaxs_2d.
    """
    image_path = image_path.expanduser().resolve()
    GIWAXS_2D_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)  # (H, W, 3), uint8

    H, W, _ = arr.shape

    # Default data region = full image
    if data_left is None:
        data_left = 0
    if data_right is None:
        data_right = W
    if data_top is None:
        data_top = 0
    if data_bottom is None:
        data_bottom = H

    if not (0 <= data_left < data_right <= W and 0 <= data_top < data_bottom <= H):
        raise ValueError(
            f"Invalid data region: left={data_left}, right={data_right}, "
            f"top={data_top}, bottom={data_bottom}, image size=({H}, {W})"
        )

    crop = arr[data_top:data_bottom, data_left:data_right, :]
    Hc, Wc, _ = crop.shape

    # Mask: True where pixel should be ignored
    if ignore_rgb is not None:
        r0, g0, b0 = ignore_rgb
        mask = (
            (crop[..., 0] == r0)
            & (crop[..., 1] == g0)
            & (crop[..., 2] == b0)
        )
    else:
        mask = np.zeros((Hc, Wc), dtype=bool)

    intensity = rgb_to_intensity(crop)  # (Hc, Wc)

    # Coordinate grids (before downsampling)
    y_indices = np.arange(Hc)
    x_indices = np.arange(Wc)

    # qz: bottom -> qz_min, top -> qz_max
    qz_grid = qz_min + (Hc - 1 - y_indices[:, None]) / (Hc - 1) * (qz_max - qz_min)
    # qxy: left -> qxy_min, right -> qxy_max
    qxy_grid = qxy_min + x_indices[None, :] / (Wc - 1) * (qxy_max - qxy_min)

    # Downsample
    step = max(1, int(downsample))
    qz_grid_ds = qz_grid[::step, ::step]
    qxy_grid_ds = qxy_grid[::step, ::step]
    intensity_ds = intensity[::step, ::step]
    mask_ds = mask[::step, ::step]

    # Flatten
    qz_flat = qz_grid_ds.ravel()
    qxy_flat = qxy_grid_ds.ravel()
    I_flat = intensity_ds.ravel()
    mask_flat = mask_ds.ravel()

    # Keep only non-masked points
    keep = ~mask_flat
    qz_flat = qz_flat[keep]
    qxy_flat = qxy_flat[keep]
    I_flat = I_flat[keep]

    out_name = f"{experiment_id}_{map_id}.csv"
    out_path = GIWAXS_2D_DIR / out_name

    with out_path.open("w", newline="") as f_out:
        writer = csv.writer(f_out)
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
        for qz_val, qxy_val, I_val in zip(qz_flat, qxy_flat, I_flat):
            writer.writerow(
                [
                    experiment_id,
                    map_id,
                    geometry,
                    q_units,
                    q_units,
                    f"{qz_val:.6g}",
                    f"{qxy_val:.6g}",
                    f"{I_val:.6g}",
                ]
            )

    rel = out_path.relative_to(REPO_ROOT)
    print(f"[2D image] wrote digitized GIWAXS map to: {rel}")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Digitize a GIWAXS 2D pattern image into a CSV (qz, qxy, intensity)."
    )
    parser.add_argument("--image", required=True, help="Path to cropped GIWAXS image (PNG/JPG)")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--map-id", default="map", help="Short id, e.g. full, masked.")
    parser.add_argument("--qz-min", type=float, required=True)
    parser.add_argument("--qz-max", type=float, required=True)
    parser.add_argument("--qxy-min", type=float, required=True)
    parser.add_argument("--qxy-max", type=float, required=True)
    parser.add_argument("--q-units", default="1/nm")
    parser.add_argument("--geometry", default="qz_qxy")
    parser.add_argument("--data-left", type=int, default=None, help="Left pixel index of data region")
    parser.add_argument("--data-right", type=int, default=None, help="Right pixel index (exclusive)")
    parser.add_argument("--data-top", type=int, default=None, help="Top pixel index of data region")
    parser.add_argument("--data-bottom", type=int, default=None, help="Bottom pixel index (exclusive)")
    parser.add_argument("--downsample", type=int, default=1, help="Pixel step size (1 = full resolution)")
    parser.add_argument(
        "--no-ignore-black",
        action="store_true",
        help="Disable masking of pure-black pixels (RGB 0,0,0).",
    )

    args = parser.parse_args()

    ignore_rgb = None if args.no_ignore_black else (0, 0, 0)

    digitize_giwaxs_image(
        image_path=Path(args.image),
        experiment_id=args.experiment_id,
        map_id=args.map_id,
        qz_min=args.qz_min,
        qz_max=args.qz_max,
        qxy_min=args.qxy_min,
        qxy_max=args.qxy_max,
        q_units=args.q_units,
        geometry=args.geometry,
        data_left=args.data_left,
        data_right=args.data_right,
        data_top=args.data_top,
        data_bottom=args.data_bottom,
        downsample=args.downsample,
        ignore_rgb=ignore_rgb,
    )


if __name__ == "__main__":
    main()