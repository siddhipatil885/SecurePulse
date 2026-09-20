"""Tests for zone geometry (point-in-polygon)."""

import pytest

from app.security.models import Point
from app.security.zones.geometry import (
    do_line_segments_intersect,
    is_point_inside_polygon,
)


# ---------------------------------------------------------------------------
# Simple rectangle: (0,0) (10,0) (10,10) (0,10)
# ---------------------------------------------------------------------------

RECT = [Point(x=0, y=0), Point(x=10, y=0), Point(x=10, y=10), Point(x=0, y=10)]


class TestPointInRectangle:

    def test_point_inside(self) -> None:
        assert is_point_inside_polygon(Point(x=5, y=5), RECT) is True

    def test_point_outside_right(self) -> None:
        assert is_point_inside_polygon(Point(x=15, y=5), RECT) is False

    def test_point_outside_above(self) -> None:
        assert is_point_inside_polygon(Point(x=5, y=-5), RECT) is False

    def test_point_outside_below(self) -> None:
        assert is_point_inside_polygon(Point(x=5, y=15), RECT) is False

    def test_point_outside_left(self) -> None:
        assert is_point_inside_polygon(Point(x=-5, y=5), RECT) is False

    def test_point_at_origin(self) -> None:
        # Vertex/edge — implementation-dependent but should not crash.
        result = is_point_inside_polygon(Point(x=0, y=0), RECT)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Triangle
# ---------------------------------------------------------------------------

TRIANGLE = [Point(x=0, y=0), Point(x=10, y=0), Point(x=5, y=10)]


class TestPointInTriangle:

    def test_inside_triangle(self) -> None:
        assert is_point_inside_polygon(Point(x=5, y=3), TRIANGLE) is True

    def test_outside_triangle(self) -> None:
        assert is_point_inside_polygon(Point(x=0, y=10), TRIANGLE) is False


# ---------------------------------------------------------------------------
# Concave (L-shaped) polygon
# ---------------------------------------------------------------------------
#   (0,0)---(6,0)
#     |       |
#   (0,4)---(3,4)
#             |
#           (3,6)---(6,6)
#                     |
#                   (6,0)  — wait, let's define this more carefully.
#
# L-shape vertices (counterclockwise):
#   (0,0) (6,0) (6,6) (3,6) (3,4) (0,4)

L_SHAPE = [
    Point(x=0, y=0),
    Point(x=6, y=0),
    Point(x=6, y=6),
    Point(x=3, y=6),
    Point(x=3, y=4),
    Point(x=0, y=4),
]


class TestPointInConcavePolygon:

    def test_inside_upper_part(self) -> None:
        # (2, 2) is inside the top rectangle of the L
        assert is_point_inside_polygon(Point(x=2, y=2), L_SHAPE) is True

    def test_inside_lower_right(self) -> None:
        # (5, 5) is inside the lower-right rectangle of the L
        assert is_point_inside_polygon(Point(x=5, y=5), L_SHAPE) is True

    def test_outside_concavity(self) -> None:
        # (1, 5) is in the concave "notch" — outside the L
        assert is_point_inside_polygon(Point(x=1, y=5), L_SHAPE) is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_fewer_than_three_vertices_returns_false(self) -> None:
        line = [Point(x=0, y=0), Point(x=10, y=10)]
        assert is_point_inside_polygon(Point(x=5, y=5), line) is False

    def test_empty_polygon(self) -> None:
        assert is_point_inside_polygon(Point(x=0, y=0), []) is False

    def test_large_polygon(self) -> None:
        """A very large rectangle still works."""
        big = [
            Point(x=0, y=0),
            Point(x=100000, y=0),
            Point(x=100000, y=100000),
            Point(x=0, y=100000),
        ]
        assert is_point_inside_polygon(Point(x=50000, y=50000), big) is True
        assert is_point_inside_polygon(Point(x=200000, y=50000), big) is False


class TestLineSegmentIntersection:

    def test_crossing_segments_intersect(self) -> None:
        assert do_line_segments_intersect(
            Point(x=0, y=5), Point(x=10, y=5),
            Point(x=5, y=0), Point(x=5, y=10),
        ) is True

    def test_endpoint_touch_intersects(self) -> None:
        assert do_line_segments_intersect(
            Point(x=0, y=0), Point(x=5, y=5),
            Point(x=5, y=5), Point(x=10, y=0),
        ) is True

    def test_parallel_segments_do_not_intersect(self) -> None:
        assert do_line_segments_intersect(
            Point(x=0, y=0), Point(x=10, y=0),
            Point(x=0, y=5), Point(x=10, y=5),
        ) is False
