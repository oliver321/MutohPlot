import pytest

from mutohplot.calibration import create_a3_calibration, create_calibration


def test_a3_calibration_document():
    doc = create_a3_calibration("norm", 5)
    assert doc.metadata["paper"] == "A3"
    assert len(doc.polylines) >= 15
    assert doc.bounds() == (0, 0, 297.0, 420.0)


@pytest.mark.parametrize(
    ("paper", "width", "height"),
    [("a3", 297.0, 420.0), ("a2", 420.0, 594.0), ("a1", 594.0, 841.0), ("a0", 841.0, 1189.0)],
)
def test_calibration_supports_all_plotter_paper_sizes(paper, width, height):
    doc = create_calibration(paper, "norm", 5)

    assert doc.metadata["paper"] == paper.upper()
    assert doc.bounds() == (0, 0, width, height)
