import argparse
from pathlib import Path
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.axes_grid1.inset_locator import inset_axes


def load_core_csv(csv_path: Path):
    """
    Expects a CSV with header and 3 columns:
      qz,qxy,intensity
    """
    data = np.genfromtxt(csv_path, delimiter=",", skip_header=1)
    if data.ndim != 2 or data.shape[1] < 3:
        raise ValueError("Expected at least 3 columns: qz,qxy,intensity")

    qz = data[:, 0].astype(float)
    qxy = data[:, 1].astype(float)
    I = data[:, 2].astype(float)

    return qz, qxy, I


def to_grid(qz, qxy, I):
    """
    Convert long-form points to a 2D grid based on unique qz/qxy values.
    Assumes qz/qxy values land on a regular grid (as produced by your digitizer).
    """
    qz_vals = np.unique(qz)
    qxy_vals = np.unique(qxy)

    qz_vals.sort()
    qxy_vals.sort()

    Z = np.full((len(qz_vals), len(qxy_vals)), np.nan, dtype=np.float32)

    iz = np.searchsorted(qz_vals, qz)
    ix = np.searchsorted(qxy_vals, qxy)

    iz = np.clip(iz, 0, len(qz_vals) - 1)
    ix = np.clip(ix, 0, len(qxy_vals) - 1)

    Z[iz, ix] = I.astype(np.float32)
    return qz_vals, qxy_vals, Z


def _connected_components(mask: np.ndarray):
    """
    4-connected components on a boolean mask.
    Returns list of components, each as list of (r,c).
    """
    H, W = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    comps = []

    for r in range(H):
        for c in range(W):
            if not mask[r, c] or visited[r, c]:
                continue
            q = deque([(r, c)])
            visited[r, c] = True
            comp = []

            while q:
                rr, cc = q.popleft()
                comp.append((rr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    r2, c2 = rr + dr, cc + dc
                    if 0 <= r2 < H and 0 <= c2 < W and mask[r2, c2] and not visited[r2, c2]:
                        visited[r2, c2] = True
                        q.append((r2, c2))

            comps.append(comp)

    return comps


def _find_best_rectangular_nan_block(
    nan_mask: np.ndarray,
    min_fill_ratio: float = 0.92,
    min_bbox_area: int = 400,
):
    """
    Pick the NaN component that is most 'rectangular':
      - large bounding box
      - high fill ratio = component_area / bbox_area
    Returns bbox indices: (rmin, rmax, cmin, cmax) inclusive.
    """
    comps = _connected_components(nan_mask)
    best = None
    best_score = -1.0

    for comp in comps:
        rows = np.array([p[0] for p in comp], dtype=int)
        cols = np.array([p[1] for p in comp], dtype=int)

        rmin, rmax = rows.min(), rows.max()
        cmin, cmax = cols.min(), cols.max()

        bbox_area = (rmax - rmin + 1) * (cmax - cmin + 1)
        if bbox_area < min_bbox_area:
            continue

        fill_ratio = len(comp) / float(bbox_area)
        if fill_ratio < min_fill_ratio:
            continue

        # Prefer big, rectangular blocks
        score = bbox_area * fill_ratio
        if score > best_score:
            best_score = score
            best = (rmin, rmax, cmin, cmax)

    return best


def _data_bbox_to_axes_fraction(ax, x0, x1, y0, y1):
    """
    Convert a bbox in data coords to (left, bottom, width, height) in axes-fraction coords.
    """
    p0_disp = ax.transData.transform((x0, y0))
    p1_disp = ax.transData.transform((x1, y1))
    inv = ax.transAxes.inverted()

    a0 = inv.transform(p0_disp)
    a1 = inv.transform(p1_disp)

    left = min(a0[0], a1[0])
    right = max(a0[0], a1[0])
    bottom = min(a0[1], a1[1])
    top = max(a0[1], a1[1])

    return left, bottom, (right - left), (top - bottom)


def plot_giwaxs(
    csv_path: Path,
    cmap_name: str = "viridis",
    vmin_percentile: float = 0.5,
    vmax_percentile: float = 99.5,
    square: bool = True,
    interpolation: str = "nearest",
    inset_colorbar: bool = True,
    cbar_width_frac: float = 0.12,   # fraction of the NaN block width
    cbar_height_frac: float = 0.65,  # fraction of the NaN block height
):
    qz, qxy, I = load_core_csv(csv_path)
    qz_vals, qxy_vals, Z = to_grid(qz, qxy, I)

    finite = np.isfinite(Z)
    if not np.any(finite):
        raise ValueError("No finite intensity values found.")

    vmin = np.percentile(Z[finite], vmin_percentile)
    vmax = np.percentile(Z[finite], vmax_percentile)

    cmap = plt.get_cmap(cmap_name).copy()

    # Keep NaNs (missing wedge, masked regions) as the LOW colormap color (NOT white)
    low = cmap(0.0)
    cmap.set_bad(low)

    Zm = np.ma.array(Z, mask=~finite)

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_facecolor(low)

    im = ax.imshow(
        Zm,
        origin="lower",
        extent=[qxy_vals.min(), qxy_vals.max(), qz_vals.min(), qz_vals.max()],
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        interpolation=interpolation,
        aspect="equal" if square else "auto",
    )

    ax.set_xlabel(r"$q_{xy}$ (1/nm)")
    ax.set_ylabel(r"$q_z$ (1/nm)")
    ax.set_title(csv_path.name)

    if square:
        ax.set_aspect("equal", adjustable="box")

    # --- Find the big rectangular NaN block on the right, paint it white, and center the colorbar in it ---
    if inset_colorbar:
        nan_mask = ~finite  # True where NaN

        bbox = _find_best_rectangular_nan_block(nan_mask)
        if bbox is None:
            # Fallback: normal outside colorbar
            cbar = fig.colorbar(im, ax=ax)
            cbar.set_label("Intensity (arb)")
        else:
            rmin, rmax, cmin, cmax = bbox

            # Convert bbox indices to data coords
            x0 = qxy_vals[cmin]
            x1 = qxy_vals[cmax]
            y0 = qz_vals[rmin]
            y1 = qz_vals[rmax]

            # Paint that NaN block white (but keep wedge etc. as low color)
            rect = Rectangle(
                (x0, y0),
                (x1 - x0),
                (y1 - y0),
                facecolor="white",
                edgecolor="none",
                zorder=3,
                transform=ax.transData,
            )
            ax.add_patch(rect)

            # Center an inset colorbar within that white rectangle
            left, bottom, w, h = _data_bbox_to_axes_fraction(ax, x0, x1, y0, y1)

            # Choose cbar size relative to the block
            cbar_w = w * cbar_width_frac
            cbar_h = h * cbar_height_frac

            cbar_left = left + (w - cbar_w) / 2.0
            cbar_bottom = bottom + (h - cbar_h) / 2.0

            cax = inset_axes(
                ax,
                width="100%",
                height="100%",
                bbox_to_anchor=(cbar_left, cbar_bottom, cbar_w, cbar_h),
                bbox_transform=ax.transAxes,
                borderpad=0.0,
            )

            cbar = fig.colorbar(im, cax=cax)
            cbar.set_label("Intensity (arb)")
    else:
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("Intensity (arb)")

    fig.tight_layout()
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Plot GIWAXS 2D from core CSV (qz,qxy,intensity).")
    parser.add_argument("--csv", required=True, help="Path to core GIWAXS CSV")
    parser.add_argument("--cmap", default="viridis", help="Matplotlib colormap (e.g. turbo, viridis, jet)")
    parser.add_argument("--vmin-percentile", type=float, default=0.5)
    parser.add_argument("--vmax-percentile", type=float, default=99.5)
    parser.add_argument("--no-square", action="store_true", help="Do not force equal aspect ratio")
    parser.add_argument("--no-inset-colorbar", action="store_true", help="Use normal outside colorbar")
    parser.add_argument("--interpolation", default="nearest", help='imshow interpolation: "nearest", "bilinear", etc.')

    # Optional tuning if you want
    parser.add_argument("--cbar-width-frac", type=float, default=0.12, help="Colorbar width as fraction of NaN block width")
    parser.add_argument("--cbar-height-frac", type=float, default=0.65, help="Colorbar height as fraction of NaN block height")

    args = parser.parse_args()

    plot_giwaxs(
        csv_path=Path(args.csv),
        cmap_name=args.cmap,
        vmin_percentile=args.vmin_percentile,
        vmax_percentile=args.vmax_percentile,
        square=not args.no_square,
        interpolation=args.interpolation,
        inset_colorbar=not args.no_inset_colorbar,
        cbar_width_frac=args.cbar_width_frac,
        cbar_height_frac=args.cbar_height_frac,
    )

#fig.savefig("giwaxs.png", dpi=300, bbox_inches="tight")

if __name__ == "__main__":
    main()