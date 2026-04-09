import numpy as np
import math


def parse_canvas_objects(objects):
    fans_circulares = []
    fans_airfree = []
    fans_ovales = []
    obstacles = []

    for obj in objects:
        obj_type = obj.get("type", "")
        left = float(obj.get("left", 0))
        top = float(obj.get("top", 0))
        scale_x = float(obj.get("scaleX", 1))
        scale_y = float(obj.get("scaleY", 1))
        angle = float(obj.get("angle", 0))
        stroke_w = float(obj.get("strokeWidth", 0))

        if obj_type == "circle":
            radius = obj.get("radius", None)
            if radius is None:
                radius = float(obj.get("width", 0)) / 2
            else:
                radius = float(radius)
            cx = left + (radius + stroke_w / 2.0) * scale_x
            cy = top + (radius + stroke_w / 2.0) * scale_y
            fans_circulares.append({
                "type": "circular",
                "x": cx,
                "y": cy,
                "r": radius * max(scale_x, scale_y),
            })

        elif obj_type == "ellipse":
            rx = float(obj.get("rx", 0)) * scale_x
            ry = float(obj.get("ry", 0)) * scale_y
            cx = left + (stroke_w / 2.0) * scale_x + rx
            cy = top + (stroke_w / 2.0) * scale_y + ry
            fans_ovales.append({
                "type": "oval",
                "x": cx,
                "y": cy,
                "rx": rx,
                "ry": ry,
                "angle": angle,
            })

        elif obj_type == "rect":
            w = float(obj.get("width", 0)) * scale_x
            h = float(obj.get("height", 0)) * scale_y
            cx = left + (stroke_w / 2.0) * scale_x + w / 2
            cy = top + (stroke_w / 2.0) * scale_y + h / 2
            fans_airfree.append({
                "type": "airfree",
                "x": cx,
                "y": cy,
                "half_w": w / 2,
                "half_h": h / 2,
                "angle": angle,
                "front_face": "right",
            })

        elif obj_type == "polygon":
            pts = []
            if "points" in obj:
                for p in obj["points"]:
                    pts.append([float(p["x"]) * scale_x + left, float(p["y"]) * scale_y + top])
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
