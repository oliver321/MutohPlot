import pytest

from mutohplot.calibration import (
    create_a3_calibration,
    create_calibration,
    create_measured_calibration,
)


def test_a3_calibration_document():
    doc = create_a3_calibration("norm", 5)
    assert doc.metadata["paper"] == "A3"
    assert len(doc.polylines) >= 15
    assert doc.bounds() == (0, 0, 297.0, 420.0)


def test_measured_calibration_uses_exact_reported_area():
    doc = create_measured_calibration(565.2, 407.59, 5)

    assert doc.metadata["page_width_mm"] == 565.2
    assert doc.metadata["page_height_mm"] == 407.59
    assert doc.metadata["hard_clip_profile"] == "Measured"
    assert doc.bounds() == (0, 0, 565.2, 407.59)


@pytest.mark.parametrize(
    ("paper", "width", "height"),
    [("a3", 297.0, 420.0), ("a2", 420.0, 594.0), ("a1", 594.0, 841.0), ("a0", 841.0, 1189.0)],
)
def test_calibration_supports_all_plotter_paper_sizes(paper, width, height):
    doc = create_calibration(paper, "norm", 5)

    assert doc.metadata["paper"] == paper.upper()
    assert doc.bounds() == (0, 0, width, height)
