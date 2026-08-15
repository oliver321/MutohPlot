import pytest

from mutohplot.hard_clip import (
    drawable_area,
    get_hard_clip,
    origin_offset_from_page_center,
)
from mutohplot.paper import get_paper


@pytest.mark.parametrize(
    "window,expected",
    [
        ("norm", (35.0, 15.0, 15.0, 15.0)),
        ("exp", (25.0, 5.0, 5.0, 5.0)),
        ("type1", (25.0, 5.0, 11.0, 11.0)),
        ("type3", (25.0, 10.0, 10.0, 10.0)),
    ],
)
def test_profiles(window, expected):
    p = get_hard_clip(window)
    assert (p.top_mm, p.bottom_mm, p.left_mm, p.right_mm) == expected


@pytest.mark.parametrize(
    "paper_name,width,height",
    [
        ("a3", 267.0, 370.0),
        ("a2", 390.0, 544.0),
        ("a1", 564.0, 791.0),
        ("a0", 811.0, 1139.0),
    ],
)
def test_norm_drawable_area_all_portrait_formats(paper_name, width, height):
    area = drawable_area(get_paper(paper_name), get_hard_clip("norm"))
    assert area.width_mm == width
    assert area.height_mm == height


@pytest.mark.parametrize("paper_name", ["a3", "a2", "a1", "a0"])
def test_landscape_still_uses_feed_direction_margins(paper_name):
    paper = get_paper(paper_name, landscape=True)
    area = drawable_area(paper, get_hard_clip("type3"))
    assert area.width_mm == paper.width_mm - 20.0
    assert area.height_mm == paper.height_mm - 35.0


def test_extra_margin_is_inside_hardware_clip():
    area = drawable_area(get_paper("a3"), get_hard_clip("norm"), 10.0)
    assert (area.x_min_mm, area.y_min_mm) == (25.0, 45.0)
    assert (area.x_max_mm, area.y_max_mm) == (272.0, 395.0)


def test_hard_clip_center_offsets():
    assert origin_offset_from_page_center(get_hard_clip("norm")) == (10.0, 0.0)
    assert origin_offset_from_page_center(get_hard_clip("exp")) == (10.0, 0.0)
    assert origin_offset_from_page_center(get_hard_clip("type1")) == (10.0, 0.0)
    assert origin_offset_from_page_center(get_hard_clip("type3")) == (7.5, 0.0)
