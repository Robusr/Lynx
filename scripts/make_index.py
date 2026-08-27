"""Build `data/index.csv` from the images in a frames directory.

Usage:
    python scripts/make_index.py [frames_dir] [out_csv]
Defaults:
    frames_dir = data/frames
    out_csv    = data/index.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXTS = (".jpg", ".jpeg", ".png", ".bmp")
INTERVAL_NS = 50_000_000  # 50 ms → 20 Hz


def main() -> None:
    frames_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/frames")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/index.csv")

    files = []
    for ext in EXTS:
        files.extend(sorted(frames_dir.glob(f"*{ext}")))

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_name", "stamp_ns"])
        for i, p in enumerate(files):
            w.writerow([p.name, i * INTERVAL_NS])
    print(f"wrote {len(files)} entries → {out}")


if __name__ == "__main__":
    main()
