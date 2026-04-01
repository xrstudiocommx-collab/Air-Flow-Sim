import numpy as np
import math
import cv2
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, Rectangle
from scipy.ndimage import distance_transform_edt

from utils.simulation import (
    compute_circular_fan_intensity,
    compute_airfree_fan_intensity,
    compute_oval_fan_intensity,
    build_transmission_mask,
    compute_visibility_with_transmission,
)


def _build_solid_mask(obstacles, height, width):
    mask = np.zeros((height, width), dtype=np.uint8)
    for obs in obstacles:
        pts = obs["points"]
        if pts.shape[0] >= 3:
            if obs["transmission"] == 0:
                cv2.fillPoly(mask, [pts], 255)
    return mask


def _build_transmission_float(obstacles, height, width):
    mask = np.ones((height, width), dtype=np.float32)
    for obs in obstacles:
        pts = obs["points"]
        if pts.shape[0] >= 3:
            region = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(region, [pts], 1)
            affected = region == 1
            mask[affected] = np.minimum(mask[affected], obs["transmission"])
    return mask


def _intensity_to_velocity_radial(intensity, grid_x, grid_y, fx, fy):
    dx = grid_x - fx
    dy = grid_y - fy
    dist = np.sqrt(dx ** 2 + dy ** 2)
    dist = np.maximum(dist, 0.1)
    vx = intensity * dx / dist
    vy = intensity * dy / dist
    return vx, vy


def _intensity_to_velocity_directional(intensity, flow_angle_rad):
    Dx = math.cos(flow_angle_rad)
    Dy = math.sin(flow_angle_rad)
    vx = intensity * Dx
    vy = intensity * Dy
    return vx, vy


def _compute_velocity_field(fans_circ, fans_airfree, fans_oval, grid_x, grid_y,
                            decay_rate, multiplier, obstacles, use_los, solid_mask):
    h, w = grid_x.shape
    vx = np.zeros((h, w), dtype=np.float32)
    vy = np.zeros((h, w), dtype=np.float32)

    transmission_mask = build_transmission_mask(obstacles, h, w) if use_los else None

    for fan in fans_circ:
        intensity = compute_circular_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier)
        if use_los and transmission_mask is not None:
            attenuation = compute_visibility_with_transmission(
                fan["x"], fan["y"], h, w, transmission_mask, num_samples=64
            )
            intensity *= attenuation
        fan_vx, fan_vy = _intensity_to_velocity_radial(intensity, grid_x, grid_y, fan["x"], fan["y"])
        vx += fan_vx
        vy += fan_vy

    for fan in fans_airfree:
        intensity = compute_airfree_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier)
        if use_los and transmission_mask is not None:
            attenuation = compute_visibility_with_transmission(
                fan["x"], fan["y"], h, w, transmission_mask, num_samples=64
            )
            intensity *= attenuation
        flow_angle_rad = math.radians(fan.get("flow_angle", 0))
        fan_vx, fan_vy = _intensity_to_velocity_directional(intensity, flow_angle_rad)
        vx += fan_vx
        vy += fan_vy

    for fan in fans_oval:
        intensity = compute_oval_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier)
        if use_los and transmission_mask is not None:
            attenuation = compute_visibility_with_transmission(
                fan["x"], fan["y"], h, w, transmission_mask, num_samples=64
            )
            intensity *= attenuation
        fan_vx, fan_vy = _intensity_to_velocity_radial(intensity, grid_x, grid_y, fan["x"], fan["y"])
        vx += fan_vx
        vy += fan_vy

    blocked = solid_mask > 200
    if np.any(blocked):
        dist_to_obs = distance_transform_edt(~blocked)
        near_obs = (dist_to_obs > 0) & (dist_to_obs < 8)
        if np.any(near_obs):
            gy_grad, gx_grad = np.gradient(dist_to_obs.astype(np.float32))
            grad_mag = np.sqrt(gx_grad ** 2 + gy_grad ** 2)
            grad_mag = np.maximum(grad_mag, 1e-6)
            gx_norm = gx_grad / grad_mag
            gy_norm = gy_grad / grad_mag

            flow_mag = np.sqrt(vx ** 2 + vy ** 2)
            dot = vx * (-gx_norm) + vy * (-gy_norm)
            push_into = dot > 0

            deflect = near_obs & push_into
            if np.any(deflect):
                tangent_x = -gy_norm
                tangent_y = gx_norm
                tang_dot = vx[deflect] * tangent_x[deflect] + vy[deflect] * tangent_y[deflect]
                sign = np.sign(tang_dot)
                sign[sign == 0] = 1

                blend = np.clip(1 - dist_to_obs[deflect] / 8, 0, 1)
                vx[deflect] = vx[deflect] * (1 - blend) + flow_mag[deflect] * sign * tangent_x[deflect] * blend
                vy[deflect] = vy[deflect] * (1 - blend) + flow_mag[deflect] * sign * tangent_y[deflect] * blend

        vx[blocked] = 0
        vy[blocked] = 0

    return vx, vy


def _apply_flow_limits_mask(vx, vy, flow_limits, sim_h, sim_w, scale_x, scale_y):
    """
    Apply flow-limit polygons to the velocity field.

    Inside a polygon the flow fades smoothly to zero at the polygon boundary
    (distance-transform-based attenuation). Outside every polygon the field is
    unchanged. If a point falls inside multiple polygons the most restrictive
    factor (minimum) is applied.

    attenuation factor range: 0 at boundary edge → 1 at polygon interior maximum.
    """
    if not flow_limits:
        return vx, vy

    # Combined attenuation grid — start fully open (no attenuation)
    attenuation = np.ones((sim_h, sim_w), dtype=np.float32)
    any_polygon_active = False

    for poly_data in flow_limits:
        raw_pts = poly_data.get("points", [])
        if len(raw_pts) < 3:
            continue

        # Scale polygon vertices to simulation grid coordinates
        pts_scaled = (np.array(raw_pts, dtype=np.float32) * np.array([scale_x, scale_y])).astype(np.int32)

        # Build inside mask using OpenCV
        inside_mask = np.zeros((sim_h, sim_w), dtype=np.uint8)
        cv2.fillPoly(inside_mask, [pts_scaled], 1)

        if not np.any(inside_mask):
            continue

        # Distance of each inside-pixel to the nearest polygon boundary
        dist_to_boundary = distance_transform_edt(inside_mask)
        max_dist = float(np.max(dist_to_boundary))
        if max_dist < 1.0:
            continue

        # Normalised factor: 0 at boundary → 1 at deepest interior point
        poly_factor = (dist_to_boundary / max_dist).astype(np.float32)

        # Apply only inside the polygon; keep the most restrictive value
        attenuation = np.where(inside_mask > 0,
                               np.minimum(attenuation, poly_factor),
                               attenuation)
        any_polygon_active = True

    if any_polygon_active:
        vx = vx * attenuation
        vy = vy * attenuation

    return vx, vy


def _trace_streamline(x0, y0, vx, vy, solid_mask, width, height, max_steps=300, dt=1.5):
    points = [(x0, y0)]
    x, y = float(x0), float(y0)

    for _ in range(max_steps):
        ix = int(np.clip(x, 0, width - 1))
        iy = int(np.clip(y, 0, height - 1))

        if solid_mask[iy, ix] > 200:
            break

        u = vx[iy, ix]
        v = vy[iy, ix]
        speed = math.sqrt(u * u + v * v)
        if speed < 0.01:
            break

        x += u / speed * dt
        y += v / speed * dt

        if x < 0 or x >= width or y < 0 or y >= height:
            break

        points.append((x, y))

    return points


def compute_streamlines(fans_circ, fans_airfree, fans_oval, obstacles,
                        img_width, img_height, decay_rate, multiplier,
                        resolution, use_los, num_lines_per_fan=40,
                        flow_limits=None):
    """
    Compute streamline traces for all fan types.

    Parameters
    ----------
    flow_limits : list[dict] | None
        Each dict must have a "points" key containing a list of [x, y] pixel
        coordinates (in original image space) that define a closed polygon.
        Inside these polygons the flow is attenuated to zero at the boundary.
    """
    res_map = {"Baja": (100, 100), "Media": (200, 200), "Alta": (400, 400)}
    sim_w, sim_h = res_map.get(resolution, (200, 200))

    scale_x = sim_w / img_width
    scale_y = sim_h / img_height

    scaled_obstacles = []
    for obs in obstacles:
        pts = (obs["points"] * np.array([scale_x, scale_y])).astype(np.int32)
        scaled_obstacles.append({
            "points": pts,
            "transmission": obs["transmission"],
            "size": obs["size"],
        })

    solid_mask = _build_solid_mask(scaled_obstacles, sim_h, sim_w)

    yy, xx = np.mgrid[0:sim_h, 0:sim_w]
    grid_x = xx.astype(np.float32)
    grid_y = yy.astype(np.float32)

    scaled_circ = [{"x": f["x"] * scale_x, "y": f["y"] * scale_y,
                     "r": f.get("r", 20) * max(scale_x, scale_y)} for f in fans_circ]
    scaled_airfree = [{
        "x": f["x"] * scale_x, "y": f["y"] * scale_y,
        "half_w": f["half_w"] * scale_x, "half_h": f["half_h"] * scale_y,
        "flow_angle": f.get("flow_angle", 0), "angle": f.get("angle", 0),
    } for f in fans_airfree]
    scaled_oval = [{"x": f["x"] * scale_x, "y": f["y"] * scale_y,
                     "rx": f.get("rx", 20) * scale_x, "ry": f.get("ry", 20) * scale_y,
                     "angle": f.get("angle", 0)} for f in fans_oval]

    vx, vy = _compute_velocity_field(scaled_circ, scaled_airfree, scaled_oval,
                                      grid_x, grid_y, decay_rate, multiplier,
                                      scaled_obstacles, use_los, solid_mask)

    # Apply flow-limit polygon attenuation to the combined velocity field
    vx, vy = _apply_flow_limits_mask(vx, vy, flow_limits or [], sim_h, sim_w, scale_x, scale_y)

    all_streamlines = []
    fan_origins = []

    for fan in scaled_circ:
        fx, fy, r = fan["x"], fan["y"], fan["r"]
        fan_origins.append({"x": fx, "y": fy, "r": max(r, 4), "type": "circ"})
        for i in range(num_lines_per_fan):
            angle = 2 * math.pi * i / num_lines_per_fan
            start_r = r * 0.9
            sx = fx + start_r * math.cos(angle)
            sy = fy + start_r * math.sin(angle)
            if 0 <= sx < sim_w and 0 <= sy < sim_h:
                pts = _trace_streamline(sx, sy, vx, vy, solid_mask, sim_w, sim_h)
                if len(pts) > 3:
                    all_streamlines.append(pts)

    for fan in scaled_airfree:
        fx, fy = fan["x"], fan["y"]
        hw, hh = fan["half_w"], fan["half_h"]
        flow_angle = math.radians(fan.get("flow_angle", 0))
        fan_origins.append({"x": fx, "y": fy, "hw": max(hw, 3), "hh": max(hh, 3), "type": "rect"})

        Dx = math.cos(flow_angle)
        Dy = math.sin(flow_angle)
        Px = -Dy
        Py = Dx
        angle_diff = flow_angle - math.radians(fan.get("angle", 0))
        aperture = hw * abs(math.sin(angle_diff)) + hh * abs(math.cos(angle_diff))
        aperture = max(aperture, 3)

        for i in range(num_lines_per_fan):
            t = -1 + 2 * i / max(num_lines_per_fan - 1, 1)
            sx = fx + Dx * 2 + Px * t * aperture
            sy = fy + Dy * 2 + Py * t * aperture
            if 0 <= sx < sim_w and 0 <= sy < sim_h:
                pts = _trace_streamline(sx, sy, vx, vy, solid_mask, sim_w, sim_h)
                if len(pts) > 3:
                    all_streamlines.append(pts)

    for fan in scaled_oval:
        fx, fy = fan["x"], fan["y"]
        r = max(fan.get("rx", 20), fan.get("ry", 20))
        fan_origins.append({"x": fx, "y": fy, "r": max(r, 4), "type": "circ"})
        for i in range(num_lines_per_fan):
            angle = 2 * math.pi * i / num_lines_per_fan
            start_r = r * 0.9
            sx = fx + start_r * math.cos(angle)
            sy = fy + start_r * math.sin(angle)
            if 0 <= sx < sim_w and 0 <= sy < sim_h:
                pts = _trace_streamline(sx, sy, vx, vy, solid_mask, sim_w, sim_h)
                if len(pts) > 3:
                    all_streamlines.append(pts)

    return all_streamlines, fan_origins, sim_w, sim_h, solid_mask, scaled_obstacles


def render_streamlines_figure(bg_image, all_streamlines, fan_origins, sim_w, sim_h,
                              img_width, img_height, obstacles, scaled_obstacles,
                              flow_limits=None, streamlines_opacity=0.7,
                              fig_bg="#1E1E2E", fig_fg="#E0E0E0"):
    """
    Render the streamlines overlay figure.

    Parameters
    ----------
    flow_limits : list[dict] | None
        Flow-limit polygons (image-space coordinates).  They are drawn as
        semi-transparent purple zones on the figure.
    streamlines_opacity : float
        Global opacity (0–1) applied to all streamline segments.
    """
    fig, ax = plt.subplots(figsize=(10, img_height / img_width * 10))
    ax.imshow(bg_image, extent=[0, sim_w, sim_h, 0], aspect="auto", alpha=0.5)

    scale_x = sim_w / img_width
    scale_y = sim_h / img_height

    # ── Obstacle outlines ──────────────────────────────────────────────────────
    for obs in obstacles:
        pts = obs["points"]
        if len(pts) >= 3:
            scaled_pts_x = [p[0] * scale_x for p in pts] + [pts[0][0] * scale_x]
            scaled_pts_y = [p[1] * scale_y for p in pts] + [pts[0][1] * scale_y]
            size_label = obs.get("size", "XL")
            color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
            ax.plot(scaled_pts_x, scaled_pts_y, color=color_map.get(size_label, "#FF0000"),
                    linewidth=2, linestyle="--", alpha=0.8)
            ax.fill(scaled_pts_x, scaled_pts_y, color=color_map.get(size_label, "#FF0000"),
                    alpha=0.15)

    # ── Flow-limit polygons ───────────────────────────────────────────────────
    # Drawn beneath the streamlines so they don't obscure the lines.
    if flow_limits:
        for idx, poly_data in enumerate(flow_limits):
            raw_pts = poly_data.get("points", [])
            if len(raw_pts) < 3:
                continue
            xs = [p[0] * scale_x for p in raw_pts] + [raw_pts[0][0] * scale_x]
            ys = [p[1] * scale_y for p in raw_pts] + [raw_pts[0][1] * scale_y]
            # Filled zone in purple
            ax.fill(xs, ys, color="#9B59B6", alpha=0.18, zorder=2)
            # Dashed boundary
            ax.plot(xs, ys, color="#9B59B6", linewidth=2, linestyle=":", alpha=0.9, zorder=2)
            # Label at centroid
            cx = sum(p[0] * scale_x for p in raw_pts) / len(raw_pts)
            cy = sum(p[1] * scale_y for p in raw_pts) / len(raw_pts)
            ax.text(cx, cy, f"Zona {idx + 1}", ha="center", va="center",
                    fontsize=7, color=fig_fg, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#6C3483", alpha=0.75),
                    zorder=3)

    # ── Streamline segments coloured by position along the line ───────────────
    segments = []
    colors = []
    for streamline in all_streamlines:
        n = len(streamline)
        for j in range(n - 1):
            segments.append([streamline[j], streamline[j + 1]])
            t = j / max(n - 1, 1)   # 0 = near fan, 1 = far away
            r_c = 0.0
            g_c = 0.8 * (1 - t * 0.5)
            b_c = 0.4 + 0.6 * t
            # Respect the user-chosen global opacity
            a_c = 0.7 * (1 - t * 0.4) * streamlines_opacity
            colors.append((r_c, g_c, b_c, a_c))

    if segments:
        lc = LineCollection(segments, colors=colors, linewidths=0.8, zorder=4)
        ax.add_collection(lc)

    # ── Fan origin markers ────────────────────────────────────────────────────
    for origin in fan_origins:
        if origin["type"] == "circ":
            circ = Circle((origin["x"], origin["y"]), origin["r"],
                          facecolor="#00FF00", edgecolor=fig_fg, lw=1.5,
                          alpha=0.85, zorder=5)
            ax.add_patch(circ)
        else:
            hw, hh = origin["hw"], origin["hh"]
            rect = Rectangle((origin["x"] - hw, origin["y"] - hh), hw * 2, hh * 2,
                              facecolor="#00FF00", edgecolor=fig_fg, lw=1.5,
                              alpha=0.85, zorder=5)
            ax.add_patch(rect)

    ax.set_xlim(0, sim_w)
    ax.set_ylim(sim_h, 0)
    ax.axis("off")
    ax.set_title("Flujo de Aire — Líneas de Corriente", fontsize=11, color=fig_fg, pad=10)

    fig.patch.set_facecolor(fig_bg)
    plt.tight_layout()
    return fig
