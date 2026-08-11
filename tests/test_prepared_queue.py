import pytest

from mutohplot.prepared_queue import PreparedQueueStore


def item(token):
    return {"token": token, "name": f"{token}.hpgl", "data": b"IN;"}


def test_queue_persists_payload_and_order(tmp_path):
    path = tmp_path / "queue.json"
    queue = PreparedQueueStore(path)
    queue.append(item("one"))
    queue.append(item("two"))
    queue.reorder(["two", "one"])

    restored = PreparedQueueStore(path)
    assert [entry["token"] for entry in restored.snapshot()] == ["two", "one"]
    assert restored.snapshot()[0]["data"] == b"IN;"

    restored.remove("two")
    assert [entry["token"] for entry in PreparedQueueStore(path).snapshot()] == ["one"]


def test_queue_rejects_incomplete_order(tmp_path):
    queue = PreparedQueueStore(tmp_path / "queue.json")
    queue.append(item("one"))

    with pytest.raises(ValueError, match="unvollständig"):
        queue.reorder([])
