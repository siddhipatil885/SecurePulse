"""
Point-in-polygon geometry using the ray-casting algorithm.

The algorithm casts a horizontal ray from the test point towards +X
and counts the number of polygon edges it crosses.  An odd crossing
count means the point is inside the polygon.

This works correctly for both convex and concave polygons.

Reference:
    https://en.wikipedia.org/wiki/Point_in_polygon#Ray_casting_algorithm
"""

from __future__ import annotations

from app.security.models import Point


def is_point_inside_polygon(point: Point, polygon: list[Point]) -> bool:
    """Return ``True`` if *point* is inside the *polygon*.

    Args:
        point: The test point (e.g. a person's bottom-center).
        polygon: Ordered list of vertices (≥ 3).  The polygon is
            implicitly closed (last vertex connects to first).

    Returns:
        ``True`` if the point is strictly inside the polygon or
        lies on an edge (best-effort — edge cases on exact
        boundaries may vary due to floating-point precision).
    """
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    px, py = point.x, point.y

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].x, polygon[i].y
        xj, yj = polygon[j].x, polygon[j].y

        # Check if the edge from vertex j to vertex i straddles the
        # horizontal ray cast from (px, py) towards +X.
        if (yi > py) != (yj > py):
            # Compute the X coordinate where the edge crosses the ray.
            x_intersect = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_intersect:
                inside = not inside

        j = i

    return inside


def _orientation(p: Point, q: Point, r: Point) -> int:
    """Find orientation of ordered triplet (p, q, r).
    Returns:
      0 : Collinear
      1 : Clockwise
      2 : Counter-clockwise
    """
    val = (q.y - p.y) * (r.x - q.x) - (q.x - p.x) * (r.y - q.y)
    if val == 0:
        return 0
    return 1 if val > 0 else 2


def _on_segment(p: Point, q: Point, r: Point) -> bool:
    """Given three collinear points p, q, r, checks if q lies on line segment 'pr'."""
    if min(p.x, r.x) <= q.x <= max(p.x, r.x) and min(p.y, r.y) <= q.y <= max(p.y, r.y):
        return True
    return False


def do_line_segments_intersect(p1: Point, q1: Point, p2: Point, q2: Point) -> bool:
    """Returns True if line segment p1q1 and p2q2 intersect."""
    o1 = _orientation(p1, q1, p2)
    o2 = _orientation(p1, q1, q2)
    o3 = _orientation(p2, q2, p1)
    o4 = _orientation(p2, q2, q1)

    # General case
    if o1 != o2 and o3 != o4:
        return True

    # Special Cases
    # p1, q1 and p2 are collinear and p2 lies on segment p1q1
    if o1 == 0 and _on_segment(p1, p2, q1):
        return True
    # p1, q1 and q2 are collinear and q2 lies on segment p1q1
    if o2 == 0 and _on_segment(p1, q2, q1):
        return True
    # p2, q2 and p1 are collinear and p1 lies on segment p2q2
    if o3 == 0 and _on_segment(p2, p1, q2):
        return True
    # p2, q2 and q1 are collinear and q1 lies on segment p2q2
    if o4 == 0 and _on_segment(p2, q1, q2):
        return True

    return False
