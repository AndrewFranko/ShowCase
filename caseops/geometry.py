"""3D artifact generation and BINARY-level change analysis.

Each resolved ticket carries two binary artifacts: the mesh as the machine
produced it (pre) and as the analyst delivered it (post) - float32 vertex
buffers, the same shape a real label store holds. The 'level of change' is
measured at two depths:

  binary level  - fixed 4KB blocks compared byte-for-byte: how much of the
                  artifact's bytes did the correction actually touch. This is
                  storage/transfer-level truth: it bounds what an incremental
                  sync or dedup layer could save.
  geometry level- how many vertices moved, and how far (mm). Clinical-ish truth.

Both are computed by the ingest job and stored per ticket, so nothing here is
recomputed per request.
"""
from __future__ import annotations

import random

import numpy as np

VERTS = 1200          # vertices per mesh; float32 xyz -> 14.4 KB per artifact
BLOCK = 4096


def make_mesh(rng: random.Random, n: int = VERTS) -> np.ndarray:
    """Synthetic coronary-ish point cloud: points along a curved tube, mm units."""
    r = np.random.default_rng(rng.getrandbits(32))
    t = np.sort(r.uniform(0, 8 * np.pi, n))
    spine = np.stack([30 * np.cos(t / 8), 30 * np.sin(t / 8), t * 1.5], axis=1)
    return (spine + r.normal(0, 1.6, (n, 3))).astype(np.float32)


def displace(mesh: np.ndarray, frac: float, mag_mm: float,
             rng: random.Random) -> np.ndarray:
    """The correction: a contiguous-ish region of the vessel is re-segmented.
    Corrections are local, not scattered - so the binary diff has structure."""
    r = np.random.default_rng(rng.getrandbits(32))
    out = mesh.copy()
    k = max(1, int(frac * len(mesh)))
    start = int(r.integers(0, max(1, len(mesh) - k)))
    idx = np.arange(start, start + k)
    out[idx] += r.normal(0, mag_mm, (len(idx), 3)).astype(np.float32)
    return out


def binary_delta(a: bytes, b: bytes, block: int = BLOCK) -> dict:
    """Byte-for-byte block comparison - what fraction of the artifact's binary
    actually changed."""
    assert len(a) == len(b), "artifacts must be same length to diff"
    av = np.frombuffer(a, dtype=np.uint8)
    bv = np.frombuffer(b, dtype=np.uint8)
    changed = av != bv
    nblocks = (len(a) + block - 1) // block
    blocks_changed = sum(
        bool(changed[i * block:(i + 1) * block].any()) for i in range(nblocks))
    return {
        "bytes_total": len(a),
        "bytes_changed": int(changed.sum()),
        "blocks_total": nblocks,
        "blocks_changed": blocks_changed,
        "blocks_changed_pct": round(100.0 * blocks_changed / nblocks, 2),
    }


def vertex_delta(pre: np.ndarray, post: np.ndarray) -> dict:
    d = np.linalg.norm(post - pre, axis=1)
    moved = d > 1e-6
    return {
        "vertices_total": len(pre),
        "vertices_moved": int(moved.sum()),
        "vertices_moved_pct": round(100.0 * moved.mean(), 2),
        "mean_disp_mm": round(float(d[moved].mean()), 3) if moved.any() else 0.0,
        "max_disp_mm": round(float(d.max()), 3),
    }
