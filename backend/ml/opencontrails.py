"""Load Google Research's OpenContrails records (GOES-16 ABI) and render ash false colour.

Layout follows the Kaggle "Google Research - Identify Contrails" release: one folder per record
with band_08.npy .. band_16.npy (H, W, T brightness temperatures, K) and human_pixel_masks.npy.
Full dataset: https://github.com/google-research/google-research/tree/master/opencontrails
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

LABELED_FRAME = 4  # index of the labelled time step in each record


def _norm(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((x - lo) / (hi - lo), 0, 1)


def ash_rgb(record: Path, frame: int = LABELED_FRAME) -> np.ndarray:
    """(H, W, 3) float image in [0, 1]. Thin ice cloud, including contrails, shows dark blue."""
    b = {n: np.load(record / f"band_{n:02d}.npy")[..., frame] for n in (11, 14, 15)}
    r = _norm(b[15] - b[14], -4, 2)
    g = _norm(b[14] - b[11], -4, 5) ** (1 / 2.5)
    bl = _norm(b[14], 243, 303)
    return np.stack([r, g, bl], axis=-1)


def mask(record: Path) -> np.ndarray:
    """(H, W) boolean contrail mask from the human labels."""
    return np.load(record / "human_pixel_masks.npy")[..., 0].astype(bool)


def records(root: Path):
    return sorted(p for p in root.iterdir() if (p / "band_14.npy").exists())
