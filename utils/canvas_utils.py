import numpy as np
import math


def parse_canvas_objects(objects):
    fans_circulares = []
    fans_airfree = []   # rectangles (AirFree pedestal fans)
    fans_ovales = []    # ellipses drawn directly
    obstacles = []

    for obj in objects:
        obj_type = obj.get("type", "")
        left = obj.get("left", 0)
        top = obj.get("top", 0)
        scale_x = obj.get("scaleX", 1)
        scale_y = obj.get("scaleY", 1)
        angle = obj.get("angle", 0)

        if obj_type == "circle":
            radius = obj.get("radius", None)
            if radius is None:
                radius = obj.get("width", 0) / 2
            fans_circulares.append({
                "type": "circular",
                "x": left + radius * scale_x,
                "y": top + radius * scale_y,
                "r": radius * max(scale_x, scale_y),
            })

        elif obj_type == "ellipse":
            rx = obj.get("rx", 0) * scale_x
            ry = obj.get("ry", 0) * scale_y
            cx = left + rx
            cy = top + ry
            fans_ovales.append({
                "type": "oval",
                "x": cx,
                "y": cy,
                "rx": rx,
                "ry": ry,
                "angle": angle,
            })

        elif obj_type == "rect":
            # AirFree pedestal fan: rectangle treated as a directional blower.
            # half_w and half_h are the semi-dimensions.
            w = obj.get("width", 0) * scale_x
            h = obj.get("height", 0) * scale_y
            cx = left + w / 2
            cy = top + h / 2
            fans_airfree.append({
                "type": "airfree",
                "x": cx,
                "y": cy,
                "half_w": w / 2,   # half width (local X axis)
                "half_h": h / 2,   # half height (local Y axis)
                "angle": angle,
                "front_face": "right",  # default; overridden by UI
            })

        elif obj_type == "polygon":
            pts = []
            if "points" in obj:
                for p in obj["points"]:
                    pts.append([p["x"] * scale_x + left, p["y"] * scale_y + top])
            if len(pts) >= 3:
                obstacles.append({
                    "points": np.array(pts, dtype=np.int32),
                    "size": "XL",
                    "transmission": 0.0,
                })

        elif obj_type == "path":
            pts = parse_path_to_points(obj.get("path", []), left, top)
            if len(pts) >= 3:
                obstacles.append({
                    "points": np.array(pts, dtype=np.int32),
                    "size": "XL",
                    "transmission": 0.0,
                })

    return fans_circulares, fans_airfree, fans_ovales, obstacles


def parse_path_to_points(path_data, left, top):
    pts = []
    for cmd in path_data:
        if len(cmd) >= 3 and cmd[0] in ("M", "L"):
            pts.append([cmd[1] + left, cmd[2] + top])
        elif len(cmd) >= 5 and cmd[0] == "Q":
            pts.append([cmd[3] + left, cmd[4] + top])
    return pts


SIZE_TRANSMISSION = {
    "Ch": 0.80,
    "M": 0.50,
    "G": 0.20,
    "XL": 0.00,
}
