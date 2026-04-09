import numpy as np
import math
import cv2
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from matplotlib.collections import LineCollection
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
    fan_influence_count = np.zeros((h, w), dtype=np.float32)
    influence_threshold = multiplier * 0.08

    transmission_mask = build_transmission_mask(obstacles, h, w) if use_los else None

    for fan in fans_circ:
        intensity = compute_circular_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier)
        if use_los and transmission_mask is not None:
            attenuation = compute_visibility_with_transmission(
                fan["x"], fan["y"], h, w, transmission_mask, num_samples=64
            )
            intensity *= attenuation
        fan_influence_count += (intensity > influence_threshold).astype(np.float32)
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
        fan_influence_count += (intensity > influence_threshold).astype(np.float32)
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
        fan_influence_count += (intensity > influence_threshold).astype(np.float32)
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

    return vx, vy, fan_influence_count


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


def _trace_streamline(x0, y0, vx, vy, solid_mask, width, height,
                      max_steps=300, dt=1.5,
                      fan_cx=None, fan_cy=None, kickstart_steps=6,
                      kickstart_dx=None, kickstart_dy=None):
    """Trace a single streamline through the velocity field.

    Parameters
    ----------
    fan_cx, fan_cy : float | None
        Centre of the originating fan.  When provided (and no explicit
        kickstart direction is given), the first *kickstart_steps* segments
        follow a purely radial direction away from the fan centre.
    kickstart_dx, kickstart_dy : float | None
        Explicit initial direction unit vector.  Overrides the radial
        direction computed from fan_cx/fan_cy.  Useful for directional
        fans (AirFree) whose initial flow is not radial.
    kickstart_steps : int
        Number of initial purely-radial/directional steps (default 6).
    """
    points = [(x0, y0)]
    x, y = float(x0), float(y0)

    # Pre-compute the initial unit vector for the kickstart phase
    use_kickstart = False
    rdx, rdy = 0.0, 0.0
    if kickstart_dx is not None and kickstart_dy is not None:
        rdx, rdy = kickstart_dx, kickstart_dy
        use_kickstart = True
    elif fan_cx is not None and fan_cy is not None:
        rdx = x0 - fan_cx
        rdy = y0 - fan_cy
        rdist = math.sqrt(rdx * rdx + rdy * rdy)
        if rdist > 0:
            rdx /= rdist
            rdy /= rdist
            use_kickstart = True

    for step in range(max_steps):
        ix = int(np.clip(x, 0, width - 1))
        iy = int(np.clip(y, 0, height - 1))

        if solid_mask[iy, ix] > 200:
            break

        u = vx[iy, ix]
        v = vy[iy, ix]
        speed = math.sqrt(u * u + v * v)
        if speed < 0.01:
            break

        # During kickstart phase, blend from pure radial toward field direction
        if use_kickstart and step < kickstart_steps:
            blend = step / kickstart_steps
            u_dir = u / speed
            v_dir = v / speed
            u_final = rdx * (1 - blend) + u_dir * blend
            v_final = rdy * (1 - blend) + v_dir * blend
            mag = math.sqrt(u_final * u_final + v_final * v_final)
            if mag > 0:
                u_final /= mag
                v_final /= mag
            x += u_final * dt
            y += v_final * dt
        else:
            x += u / speed * dt
            y += v / speed * dt

        if x < 0 or x >= width or y < 0 or y >= height:
            break

        points.append((x, y))

    return points


def compute_streamlines(fans_circ, fans_airfree, fans_oval, obstacles,
                        img_width, img_height, decay_rate, multiplier,
                        resolution, use_los, num_lines_per_fan=80,
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
    # Compute simulation grid preserving image aspect ratio so circles stay round
    base_res = {"Baja": 100, "Media": 200, "Alta": 400}.get(resolution, 200)
    aspect = img_width / max(img_height, 1)
    if aspect >= 1:
        sim_w = base_res
        sim_h = max(int(base_res / aspect), 1)
    else:
        sim_h = base_res
        sim_w = max(int(base_res * aspect), 1)

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

    # With aspect-preserving grid, scale_x ≈ scale_y; use average for radius
    uniform_scale = (scale_x + scale_y) / 2.0
    scaled_circ = [{"x": f["x"] * scale_x, "y": f["y"] * scale_y,
                     "r": f.get("r", 20) * uniform_scale} for f in fans_circ]
    scaled_airfree = [{
        "x": f["x"] * scale_x, "y": f["y"] * scale_y,
        "half_w": f["half_w"] * scale_x, "half_h": f["half_h"] * scale_y,
        "flow_angle": f.get("flow_angle", 0), "angle": f.get("angle", 0),
    } for f in fans_airfree]
    scaled_oval = [{"x": f["x"] * scale_x, "y": f["y"] * scale_y,
                     "rx": f.get("rx", 20) * scale_x,
                     "ry": f.get("ry", 20) * scale_y,
                     "angle": f.get("angle", 0)} for f in fans_oval]

    vx, vy, convergence_map = _compute_velocity_field(scaled_circ, scaled_airfree, scaled_oval,
                                      grid_x, grid_y, decay_rate, multiplier,
                                      scaled_obstacles, use_los, solid_mask)

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
                pts = _trace_streamline(sx, sy, vx, vy, solid_mask, sim_w, sim_h,
                                        fan_cx=fx, fan_cy=fy)
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
                pts = _trace_streamline(sx, sy, vx, vy, solid_mask, sim_w, sim_h,
                                        fan_cx=fx, fan_cy=fy,
                                        kickstart_dx=Dx, kickstart_dy=Dy)
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
                pts = _trace_streamline(sx, sy, vx, vy, solid_mask, sim_w, sim_h,
                                        fan_cx=fx, fan_cy=fy)
                if len(pts) > 3:
                    all_streamlines.append(pts)

    return all_streamlines, fan_origins, sim_w, sim_h, solid_mask, scaled_obstacles, convergence_map


def render_streamlines_figure(bg_image, all_streamlines, fan_origins, sim_w, sim_h,
                              img_width, img_height, obstacles, scaled_obstacles,
                              flow_limits=None, streamlines_opacity=0.7,
                              streamlines_decay=0.10,
                              convergence_map=None,
                              fig_bg="#1E1E2E", fig_fg="#E0E0E0"):
    """
    Render the streamlines overlay figure.

    All rendering is done in image-pixel coordinates so that fan positions
    match exactly where they were drawn on the canvas.

    Parameters
    ----------
    flow_limits : list[dict] | None
        Flow-limit polygons (image-space coordinates).  They are drawn as
        semi-transparent purple zones on the figure.
    streamlines_opacity : float
        Global opacity (0–1) applied to all streamline segments.
    streamlines_decay : float
        Exponential decay rate for streamline intensity (affects colour fade).
        Lower values → lines stay visible longer; higher → fade quickly.
    convergence_map : np.ndarray | None
        2-D array (sim_h × sim_w) counting how many fans influence each pixel.
        Segments in regions where convergence >= 2 are coloured navy blue.
    """
    fig, ax = plt.subplots(figsize=(10, img_height / img_width * 10))
    ax.imshow(bg_image, extent=[0, img_width, img_height, 0])

    inv_sx = img_width / sim_w
    inv_sy = img_height / sim_h

    for obs in obstacles:
        pts = obs["points"]
        if len(pts) >= 3:
            obs_x = [p[0] for p in pts] + [pts[0][0]]
            obs_y = [p[1] for p in pts] + [pts[0][1]]
            size_label = obs.get("size", "XL")
            color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
            ax.plot(obs_x, obs_y, color=color_map.get(size_label, "#FF0000"),
                    linewidth=2, linestyle="--", alpha=0.8)
            ax.fill(obs_x, obs_y, color=color_map.get(size_label, "#FF0000"),
                    alpha=0.15)

    if flow_limits:
        for idx, poly_data in enumerate(flow_limits):
            raw_pts = poly_data.get("points", [])
            if len(raw_pts) < 3:
                continue
            xs = [p[0] for p in raw_pts] + [raw_pts[0][0]]
            ys = [p[1] for p in raw_pts] + [raw_pts[0][1]]
            ax.fill(xs, ys, color="#9B59B6", alpha=0.18, zorder=2)
            ax.plot(xs, ys, color="#9B59B6", linewidth=2, linestyle=":", alpha=0.9, zorder=2)
            cx = sum(p[0] for p in raw_pts) / len(raw_pts)
            cy = sum(p[1] for p in raw_pts) / len(raw_pts)
            ax.text(cx, cy, f"Zona {idx + 1}", ha="center", va="center",
                    fontsize=7, color=fig_fg, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#6C3483", alpha=0.75),
                    zorder=3)

    has_conv = convergence_map is not None
    conv_h, conv_w = (convergence_map.shape if has_conv else (0, 0))

    # Color gradient: navy blue (near fan) → green (mid) → transparent (far)
    segments = []
    colors = []
    linewidths = []
    for streamline in all_streamlines:
        n = len(streamline)
        for j in range(n - 1):
            sim_px, sim_py = streamline[j]
            sim_px2, sim_py2 = streamline[j + 1]
            # Convert segment endpoints from simulation to image-pixel coords
            seg_start = (sim_px * inv_sx, sim_py * inv_sy)
            seg_end = (sim_px2 * inv_sx, sim_py2 * inv_sy)
            segments.append([seg_start, seg_end])
            t = j / max(n - 1, 1)
            intensity = math.exp(-streamlines_decay * j)

            is_convergence = False
            conv_strength = 0
            if has_conv:
                ix = int(np.clip(sim_px, 0, conv_w - 1))
                iy = int(np.clip(sim_py, 0, conv_h - 1))
                conv_strength = convergence_map[iy, ix]
                is_convergence = conv_strength >= 2

            r_c = 0.0
            g_c = 0.60 * t * intensity
            b_c = 0.55 * (1.0 - t) * intensity

            if is_convergence:
                boost = 1.0 + (conv_strength - 1) * 0.5
                g_c = max(g_c / max(intensity, 1e-6), 0.15) * intensity * boost
                b_c = max(b_c / max(intensity, 1e-6), 0.30) * intensity * boost
                r_c = 0.0
                a_c = min(0.90, 0.65 * boost) * intensity * streamlines_opacity
                lw = 1.4
            else:
                a_c = intensity * 0.60 * streamlines_opacity
                lw = 0.8

            colors.append((r_c, g_c, b_c, a_c))
            linewidths.append(lw)

    if segments:
        lc = LineCollection(segments, colors=colors, linewidths=linewidths, zorder=4)
        ax.add_collection(lc)

    if has_conv and np.any(convergence_map >= 2):
        conv_display = np.where(convergence_map >= 2, convergence_map, np.nan)
        ax.imshow(conv_display, extent=[0, img_width, img_height, 0], aspect="auto",
                  cmap="Blues", alpha=0.12, zorder=3, interpolation="bilinear")

    ax.set_xlim(0, img_width)
    ax.set_ylim(img_height, 0)
    ax.axis("off")
    ax.set_title("Flujo de Aire — Líneas de Corriente", fontsize=11, color=fig_fg, pad=10)

    fig.patch.set_facecolor(fig_bg)
    plt.tight_layout()
    return fig
