"""Fetch real street-scene frames for the demo (COCO val2017 subset).

Downloads the official COCO val2017 instance annotations, uses them to pick the
busiest street scenes (cars / pedestrians / trucks / buses / motorcycles /
bicycles), downloads only those images, keeps the ones the offline model
actually detects, and writes a replay-ready `data/frames/` + `data/index.csv`.

Why this approach: COCO val2017 image IDs are extremely sparse (probing 1870
consecutive IDs found 10 real images), so guessing IDs is hopeless. The
annotations JSON gives the authoritative ID list, so we download only what
exists.

Usage:
    python scripts/fetch_demo_data.py [--keep N] [--annotations PATH]

Defaults:
    keep        = 15   images to keep
    annotations = data/annotations/instances_val2017.json (auto-downloaded
                  from the HF mirror if missing)
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

COCO_IMG = "http://images.cocodataset.org/val2017/{name}"
ANNOTATIONS_URL = (
    "https://hf-mirror.com/datasets/LibreYOLO/coco2017/resolve/main/instances_val2017.json"
)
KEEP_CLASSES = {"person", "car", "truck", "bus", "motorcycle", "bicycle"}
INTERVAL_NS = 50_000_000  # 20 Hz
UA = {"User-Agent": "lynx-fetch/1.0"}


def _load_annotations(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading annotations → {path}")
        req = urllib.request.Request(ANNOTATIONS_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path


def _target_images(annotations_path: Path) -> list[dict]:
    data = json.loads(annotations_path.read_text(encoding="utf-8"))
    cat = {c["id"]: c["name"] for c in data["categories"]}
    keep_ids = {i for i, n in cat.items() if n in KEEP_CLASSES}
    img_by_id = {x["id"]: x for x in data["images"]}

    counts: dict[int, Counter] = defaultdict(Counter)
    for a in data["annotations"]:
        if a["category_id"] in keep_ids:
            counts[a["image_id"]][cat[a["category_id"]]] += 1

    ranked = sorted(counts.items(), key=lambda kv: -sum(kv[1].values()))
    return [
        {"image_id": iid, "name": img_by_id[iid]["file_name"], "counts": dict(cnt)}
        for iid, cnt in ranked
    ]


def _select(ranked: list[dict], keep: int) -> list[dict]:
    """Top `keep*2` busiest scenes, sampled evenly for density variety."""
    top = ranked[: keep * 2]
    return [top[int(i * len(top) / keep)] for i in range(keep)]


def _download(name: str, dest: Path) -> bool:
    req = urllib.request.Request(COCO_IMG.format(name=name), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        return cv2.imread(str(dest)) is not None
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=15)
    ap.add_argument("--annotations", type=Path, default=Path("data/annotations/instances_val2017.json"))
    args = ap.parse_args()

    ann = _load_annotations(args.annotations)
    ranked = _target_images(ann)
    print(f"{len(ranked)} val2017 images contain target classes")

    candidates = _select(ranked, args.keep)
    tmp = Path("/tmp/lynx_coco")
    tmp.mkdir(parents=True, exist_ok=True)

    downloaded: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_download, c["name"], tmp / c["name"]): c for c in candidates}
        for fut in as_completed(futs):
            c = futs[fut]
            if fut.result():
                downloaded.append(c)
    downloaded.sort(key=lambda c: -sum(c["counts"].values()))
    print(f"downloaded {len(downloaded)}/{len(candidates)} images")

    # keep those the offline model actually detects cars/pedestrians in
    from sdk.backend.offline import OfflineBackend
    from sdk.config import load_config

    cfg = load_config("config/robot.demo.yaml")
    be = OfflineBackend()
    be.init(cfg)

    kept: list[dict] = []
    for c in downloaded:
        dets = be.detect(cv2.imread(str(tmp / c["name"])))
        hits = [d for d in dets if d.cls_name in KEEP_CLASSES and d.confidence >= 0.3]
        if hits:
            c["hits"] = [(d.cls_name, round(d.confidence, 2)) for d in hits[:6]]
            kept.append(c)
            print(f"  keep {c['name']}: {c['hits']}")
        if len(kept) >= args.keep:
            break
    be.release()

    # write replay set
    frames_dir = Path("data/frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("*.jpg"):
        old.unlink()
    index_path = Path("data/index.csv")
    with open(index_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_name", "stamp_ns"])
        for k, c in enumerate(kept):
            name = f"frame_{k:06d}.jpg"
            shutil.copy(tmp / c["name"], frames_dir / name)
            w.writerow([name, k * INTERVAL_NS])
    print(f"wrote {len(kept)} real frames → {frames_dir} + {index_path}")


if __name__ == "__main__":
    main()
