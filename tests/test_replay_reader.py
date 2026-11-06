"""Replay reader tests; camera decoding is stubbed so OpenCV is not required."""
import numpy as np

from sdk.input.replay_reader import ReplayReader


def _reader(tmp_path, rows: str, loop: bool = False) -> ReplayReader:
    index = tmp_path / "index.csv"
    index.write_text(rows, encoding="utf-8")
    return ReplayReader(str(tmp_path), str(index), loop=loop)


def test_reads_index_rows_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ReplayReader,
        "_read_camera",
        lambda self, entry: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    reader = _reader(
        tmp_path,
        "frame_name,stamp_ns\nframe_000000.jpg,10\nframe_000001.jpg,20\n",
    )
    batches = list(reader)
    assert [b.stamp_ns for b in batches] == [10, 20]
    assert len(reader) == 2


def test_loop_wraps_to_first_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ReplayReader,
        "_read_camera",
        lambda self, entry: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    reader = _reader(
        tmp_path,
        "frame_name,stamp_ns\nframe_000000.jpg,10\nframe_000001.jpg,20\n",
        loop=True,
    )
    assert next(reader).stamp_ns == 10
    assert next(reader).stamp_ns == 20
    assert next(reader).stamp_ns == 10


def test_glob_mode_without_index(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ReplayReader,
        "_read_camera",
        lambda self, entry: np.zeros((2, 2, 3), dtype=np.uint8),
    )
    (tmp_path / "a.jpg").write_bytes(b"")
    (tmp_path / "b.jpg").write_bytes(b"")
    reader = ReplayReader(str(tmp_path), None, loop=False)
    assert len(reader) == 2
    assert [b.stamp_ns for b in reader] == [0, 50_000_000]
