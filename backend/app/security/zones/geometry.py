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
