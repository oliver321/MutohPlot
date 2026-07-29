from mutohplot.calibration import create_a3_calibration


def test_a3_calibration_document():
    doc = create_a3_calibration("norm", 5)
    assert doc.metadata["paper"] == "A3"
    assert len(doc.polylines) >= 15
    assert doc.bounds() == (0, 0, 297.0, 420.0)
