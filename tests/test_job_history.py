import json

import pytest

from mutohplot.job_history import JobHistory


def test_history_persists_newest_jobs_and_updates(tmp_path):
    path = tmp_path / "jobs.json"
    history = JobHistory(path, limit=2)
    history.add({"id": "one", "status": "prepared"})
    history.add({"id": "two", "status": "prepared"})
    history.add({"id": "three", "status": "prepared"})
    history.update("three", status="complete")

    reloaded = JobHistory(path, limit=2)
    assert [job["id"] for job in reloaded.snapshot()] == ["three", "two"]
    assert reloaded.snapshot()[0]["status"] == "complete"
    assert json.loads(path.read_text())[0]["id"] == "two"


def test_history_rejects_corrupt_file(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(ValueError, match="Auftragsverlauf"):
        JobHistory(path)
