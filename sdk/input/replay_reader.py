"""Replay data source: plays back recorded frames for the demo/CI loop.

Reads an `index.csv` (columns: `frame_name`, `stamp_ns`, optionally `camera`)
or, absent one, globs images in `frames_dir` and synthesizes a monotonic stamp.
Loopable so the dashboard has a continuous stream without a live vehicle.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

import numpy as np


@dataclass
class FrameBatch:
    """Time-aligned frame bundle for one perception tick.

    Demo subset of the doc's FrameBatch (§3.1): a single camera + optional lidar
    array stand in for the doc's `cams[]/lidars[]/radars[]/imus[]` vectors, which
    arrive with real multi-sensor drivers (M2).
    """
    stamp_ns: int
    camera: Optional[np.ndarray] = None
    lidar: Optional[np.ndarray] = None
    frame_name: str = ""
    frame_id: str = ""  # source sensor frame (e.g. "camera"); output frame is cfg.output.frame_id


class ReplayReader:
    def __init__(
        self,
        frames_dir: str,
        index_path: Optional[str] = None,
        loop: bool = True,
        default_interval_ns: int = 50_000_000,
    ):
        self.frames_dir = Path(frames_dir)
        self.loop = loop
        self.default_interval_ns = default_interval_ns
        self._entries: List[dict] = self._load(index_path)
        self._i = 0

    def _load(self, index_path: Optional[str]) -> List[dict]:
        if index_path and Path(index_path).exists():
            with open(index_path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))

        exts = ("*.jpg", "*.jpeg", "*.png", "*.bmp")
        files: List[Path] = []
        for ext in exts:
            files.extend(sorted(self.frames_dir.glob(ext)))
        return [
            {
                "frame_name": p.name,
                "stamp_ns": i * self.default_interval_ns,
            }
            for i, p in enumerate(files)
        ]

    def _read_camera(self, entry: dict) -> Optional[np.ndarray]:
        name = entry.get("camera") or entry.get("frame_name")
        if not name:
            return None
        try:
            import cv2
        except ImportError as e:  # pragma: no cover - depends on env
            raise RuntimeError("opencv-python is required to read frames.") from e
        path = self.frames_dir / name
        if not path.exists():
            return None
        return cv2.imread(str(path))

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> "ReplayReader":
        return self

    def __next__(self) -> FrameBatch:
        if not self._entries:
            raise StopIteration
        if self._i >= len(self._entries):
            if self.loop:
                self._i = 0
            else:
                raise StopIteration
        entry = self._entries[self._i]
        self._i += 1
        return FrameBatch(
            stamp_ns=int(entry.get("stamp_ns", 0)),
            camera=self._read_camera(entry),
            frame_name=entry.get("frame_name", ""),
        )
