from __future__ import annotations

import math
from typing import Sequence
from .types import AnchorType, Point


def normalize_coordinates(x: float, y: float, width: int, height: int) -> Point:
    w = max(1, width)
    h = max(1, height)
    norm_x = max(0.0, min(1.0, float(x) / w))
    norm_y = max(0.0, min(1.0, float(y) / h))
    return Point(norm_x, norm_y)


def denormalize_coordinates(p_or_x: Any, y_or_width: Any, width_or_height: int = 1, height: int = 1) -> tuple[float, float]:
    if isinstance(p_or_x, Point) or (hasattr(p_or_x, "x") and hasattr(p_or_x, "y")):
        return float(p_or_x.x) * float(y_or_width), float(p_or_x.y) * float(width_or_height)
    return float(p_or_x) * float(width_or_height), float(y_or_width) * float(height)


def bounding_box_anchor(
    bbox_xyxy: tuple[float, float, float, float] | list[float],
    anchor_type: Any = AnchorType.BOTTOM_CENTER,
    width: int = 1,
    height: int = 1,
    custom_ratio: tuple[float, float] = (0.5, 1.0),
) -> Point:
    """Calculate the normalized anchor point for a bounding box [x1, y1, x2, y2]."""
    if isinstance(anchor_type, (int, float)) and isinstance(width, (int, float)):
        w_val = int(anchor_type)
        h_val = int(width)
        atype = height if isinstance(height, (AnchorType, str)) else AnchorType.BOTTOM_CENTER
        w = max(1, w_val)
        h = max(1, h_val)
        anchor_type = atype
    else:
        w = max(1, width)
        h = max(1, height)

    x1, y1, x2, y2 = bbox_xyxy
    if str(anchor_type) == str(AnchorType.BOTTOM_CENTER):
        ax = (x1 + x2) / 2.0
        ay = y2
    elif str(anchor_type) == str(AnchorType.CENTER):
        ax = (x1 + x2) / 2.0
        ay = (y1 + y2) / 2.0
    elif str(anchor_type) == str(AnchorType.CUSTOM):
        rx, ry = custom_ratio
        ax = x1 + (x2 - x1) * rx
        ay = y1 + (y2 - y1) * ry
    else:
        ax = (x1 + x2) / 2.0
        ay = y2

    # If coordinates are already normalized (all <= 1.0 and width=height=1)
    if w == 1 and h == 1 and x2 <= 1.0 and y2 <= 1.0:
        return Point(max(0.0, min(1.0, ax)), max(0.0, min(1.0, ay)))

    return normalize_coordinates(ax, ay, w, h)


def signed_line_side(p: Point, a: Point, b: Point) -> float:
    """Signed cross product in screen coordinates (x right, y down).

    Returns:
    > 0: point p is to the left of directed segment a -> b (in screen space)
    < 0: point p is to the right of directed segment a -> b (in screen space)
    = 0: point p is collinear with a -> b
    """
    return (p.x - a.x) * (b.y - a.y) - (p.y - a.y) * (b.x - a.x)


def signed_line_distance(p: Point, a: Point, b: Point) -> float:
    """Perpendicular signed distance from point p to line a -> b in normalized space."""
    dx = b.x - a.x
    dy = b.y - a.y
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0
    return signed_line_side(p, a, b) / length


def _ccw(a: Point, b: Point, c: Point) -> bool:
    return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x)


def segment_intersection(p1: Point, p2: Point, p3: Point, p4: Point) -> tuple[bool, Point | None]:
    """Test if segment p1-p2 intersects segment p3-p4 and compute intersection point."""
    d1 = (p2.x - p1.x, p2.y - p1.y)
    d2 = (p4.x - p3.x, p4.y - p3.y)

    det = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(det) < 1e-9:
        return False, None  # Collinear or parallel

    dx = p3.x - p1.x
    dy = p3.y - p1.y

    t1 = (dx * d2[1] - dy * d2[0]) / det
    t2 = (dx * d1[1] - dy * d1[0]) / det

    if 0.0 <= t1 <= 1.0 and 0.0 <= t2 <= 1.0:
        ix = p1.x + t1 * d1[0]
        iy = p1.y + t1 * d1[1]
        return True, Point(ix, iy)

    return False, None


def distance_point_to_segment(p: Point, a: Point, b: Point) -> float:
    """Euclidean distance from point p to segment a -> b."""
    dx = b.x - a.x
    dy = b.y - a.y
    l2 = dx * dx + dy * dy
    if l2 < 1e-9:
        return math.hypot(p.x - a.x, p.y - a.y)
    t = max(0.0, min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2))
    proj_x = a.x + t * dx
    proj_y = a.y + t * dy
    return math.hypot(p.x - proj_x, p.y - proj_y)


def point_in_polygon(point: Point, polygon: Sequence[Point], margin: float = 0.0) -> bool:
    """Ray casting algorithm with optional boundary margin hysteresis.

    If margin > 0: point must be strictly inside and at least `margin` distance away from boundary.
    If margin < 0: point is considered inside if within `abs(margin)` of outer boundary.
    """
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    p1 = polygon[0]
    for i in range(1, n + 1):
        p2 = polygon[i % n]
        if point.y > min(p1.y, p2.y):
            if point.y <= max(p1.y, p2.y):
                if point.x <= max(p1.x, p2.x):
                    if p1.y != p2.y:
                        x_inters = (point.y - p1.y) * (p2.x - p1.x) / (p2.y - p1.y) + p1.x
                    if p1.x == p2.x or point.x <= x_inters:
                        inside = not inside
        p1 = p2

    if abs(margin) < 1e-6:
        return inside

    # Boundary margin hysteresis check
    min_dist = float("inf")
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        dist = distance_point_to_segment(point, a, b)
        if dist < min_dist:
            min_dist = dist

    if margin > 0:
        # Require being inside and away from edges
        return inside and (min_dist >= margin)
    else:
        # Relaxed: inside OR close to boundary outside
        return inside or (min_dist <= abs(margin))


def polygon_area(polygon: Sequence[Point]) -> float:
    """Calculate Shoelace formula area of a 2D polygon."""
    n = len(polygon)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += polygon[i].x * polygon[j].y
        area -= polygon[j].x * polygon[i].y
    return abs(area) / 2.0


def polygon_validation(polygon: Sequence[Point]) -> tuple[bool, str]:
    """Validate that polygon vertices form a valid non-degenerate simple polygon."""
    if len(polygon) < 3:
        return False, f"Polygon must have at least 3 vertices, got {len(polygon)}"

    # Check bounds
    for i, p in enumerate(polygon):
        if not (0.0 <= p.x <= 1.0 and 0.0 <= p.y <= 1.0):
            return False, f"Vertex {i} ({p.x}, {p.y}) outside normalized coordinates [0.0, 1.0]"

    # Check for self-intersections
    n = len(polygon)
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        for j in range(i + 2, n):
            if (i == 0 and j == n - 1):
                continue  # Consecutive edges at wrap-around
            p3 = polygon[j]
            p4 = polygon[(j + 1) % n]
            intersects, _ = segment_intersection(p1, p2, p3, p4)
            if intersects:
                return False, f"Polygon is self-intersecting between edge {i}-{(i+1)%n} and edge {j}-{(j+1)%n}"

    # Check area
    area = polygon_area(polygon)
    if area < 1e-6:
        return False, "Polygon has zero or near-zero area"

    return True, "Valid polygon"


def line_validation(a: Point, b: Point) -> tuple[bool, str]:
    """Validate virtual line endpoints."""
    if not (0.0 <= a.x <= 1.0 and 0.0 <= a.y <= 1.0):
        return False, f"Point A ({a.x}, {a.y}) outside normalized coordinates [0.0, 1.0]"
    if not (0.0 <= b.x <= 1.0 and 0.0 <= b.y <= 1.0):
        return False, f"Point B ({b.x}, {b.y}) outside normalized coordinates [0.0, 1.0]"

    length = math.hypot(b.x - a.x, b.y - a.y)
    if length < 1e-4:
        return False, f"Line is degenerate (length {length:.6f} < 1e-4)"

    return True, "Valid virtual line"
