from mutohplot.paper import get_paper


def test_a2_landscape():
    p = get_paper("a2", True)
    assert (p.width_mm, p.height_mm) == (594.0, 420.0)
