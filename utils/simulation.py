import numpy as np
import cv2
import math


def compute_circular_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier):
    fx, fy = fan["x"], fan["y"]
    radius = fan.get("r", 0)
    dist = np.sqrt((grid_x - fx) ** 2 + (grid_y - fy) ** 2)

    intensity = np.zeros_like(dist, dtype=np.float32)
    interior = dist <= radius
    intensity[interior] = multiplier
    exterior = dist > radius
    intensity[exterior] = multiplier * np.exp(-(dist[exterior] - radius) * decay_rate)

    return intensity


def compute_airfree_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier):
    """
    AirFree pedestal fan — elliptical heat-transfer model.

    The rectangle defines the fan body. The flow originates at the BACK FACE
    (face opposite to flow direction) and blows toward the FRONT FACE.

    Coordinate system (flow-aligned, origin at back-face center):
        x_flow = distance along flow direction (0 = back face, 2*u_extent = front face)
        y_flow = perpendicular distance from flow axis

    Elliptical distance:
        x_norm = x_flow / (2 * u_extent)
        y_norm = y_flow / v_extent
        dist_elip = sqrt(x_norm² + y_norm²)

    Intensity rules:
        dist_elip <= 1  → multiplier  (core zone: inside the flow ellipse / rect interior)
        dist_elip >  1  → multiplier * exp(-(dist_elip - 1) * decay)
        x_flow < 0      → 0  (no air behind the back face)

    a = 2 * u_extent  (length of core along flow)
    b = v_extent      (lateral half-width of aperture)
    """
    cx, cy = fan["x"], fan["y"]
    half_w = max(fan["half_w"], 1)
    half_h = max(fan["half_h"], 1)
    rect_angle = math.radians(fan.get("angle", 0))
    flow_angle_rad = math.radians(fan.get("flow_angle", 0))

    # Flow unit vector and its perpendicular
    Dx = math.cos(flow_angle_rad)
    Dy = math.sin(flow_angle_rad)
    Px = -Dy  # perpendicular (90° CCW)
    Py = Dx

    # Grid in flow-aligned coords centered at fan
    gx = grid_x - cx
    gy = grid_y - cy
    u = gx * Dx + gy * Dy   # along flow
    v = gx * Px + gy * Py   # perpendicular

    # Rectangle bounding extents in flow-aligned coords
    angle_diff = flow_angle_rad - rect_angle
    cos_d = math.cos(angle_diff)
    sin_d = math.sin(angle_diff)
    u_extent = half_w * abs(cos_d) + half_h * abs(sin_d)  # half-length along flow
    v_extent = half_w * abs(sin_d) + half_h * abs(cos_d)  # lateral half-width

    # x_flow: distance along flow from the back face (back face = -u_extent in u coords)
    x_flow = u + u_extent   # 0 at back face, 2*u_extent at front face

    # Normalised elliptical coordinates
    a = 2.0 * u_extent   # full length of core
    b = v_extent          # lateral semi-axis (aperture half-width)

    x_norm = x_flow / a
    y_norm = v / b
    dist_elip = np.sqrt(x_norm ** 2 + y_norm ** 2)

    intensity = np.zeros_like(dist_elip, dtype=np.float32)

    # Core: elliptical interior (dist_elip <= 1) AND in front of back face
    core = (dist_elip <= 1.0) & (x_flow >= 0)
    intensity[core] = multiplier

    # Decay zone: outside ellipse but still in front of back face
    decay_zone = (dist_elip > 1.0) & (x_flow >= 0)
    intensity[decay_zone] = multiplier * np.exp(
        -(dist_elip[decay_zone] - 1.0) * decay_rate * max(a, b)
    )
    # x_flow < 0 (behind back face) stays at 0

    return intensity


def compute_oval_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier):
    fx, fy = fan["x"], fan["y"]
    rx, ry = fan["rx"], fan["ry"]
    angle_rad = math.radians(fan.get("angle", 0))

    dx = grid_x - fx
    dy = grid_y - fy

    cos_a = math.cos(-angle_rad)
    sin_a = math.sin(-angle_rad)
    dx_rot = dx * cos_a - dy * sin_a
    dy_rot = dx * sin_a + dy * cos_a

    a = max(rx, 1)
    b = max(ry, 1)

    norm_dist = np.sqrt((dx_rot / a) ** 2 + (dy_rot / b) ** 2)

    intensity = np.zeros_like(norm_dist, dtype=np.float32)
    interior = norm_dist <= 1.0
    intensity[interior] = multiplier
    exterior = norm_dist > 1.0
    intensity[exterior] = multiplier * np.exp(
        -(norm_dist[exterior] - 1.0) * decay_rate * max(a, b)
    )

    # Smooth directional bias via sigmoid on cosine of angle
    angle = np.arctan2(dy_rot, dx_rot)
    cos_angle = np.cos(angle)
    directional = 0.3 + 0.7 / (1.0 + np.exp(-4.0 * cos_angle))
    intensity *= directional

    return intensity


def build_transmission_mask(obstacles, height, width):
    mask = np.ones((height, width), dtype=np.float32)
    for obs in obstacles:
        transmission = obs["transmission"]
        pts = obs["points"]
        if pts.shape[0] >= 3:
            obs_region = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(obs_region, [pts], 1)
            affected = obs_region == 1
            mask[affected] = np.minimum(mask[affected], transmission)
    return mask


def compute_visibility_with_transmission(fan_x, fan_y, height, width, transmission_mask, num_samples=64):
    """
    Trace rays from (fan_x, fan_y) to every grid cell, accumulating
    the minimum transmission value encountered along each ray.
    """
    attenuation = np.ones((height, width), dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    dx = xx.astype(np.float32) - fan_x
    dy = yy.astype(np.float32) - fan_y

    for i in range(1, num_samples + 1):
        t = i / num_samples
        sx = np.clip((fan_x + t * dx).astype(np.int32), 0, width - 1)
        sy = np.clip((fan_y + t * dy).astype(np.int32), 0, height - 1)
        sample_trans = transmission_mask[sy, sx]
        blocked = sample_trans < 1.0
        attenuation[blocked] = np.minimum(attenuation[blocked], sample_trans[blocked])

    return attenuation


def _apply_los(los_x, los_y, intensity, sim_h, sim_w, obstacles, obstacle_mask_full,
               scaled_obstacles, use_los, transmission_mask=None, num_samples=48):
    xl_blocked = np.zeros((sim_h, sim_w), dtype=bool)
    if use_los and len(obstacles) > 0:
        att = compute_visibility_with_transmission(
            los_x, los_y, sim_h, sim_w, transmission_mask, num_samples=num_samples
        )
        inside_obs = transmission_mask < 1.0
        att[inside_obs] = np.minimum(att[inside_obs], transmission_mask[inside_obs])
        xl_blocked = att == 0
        intensity *= att
    elif transmission_mask is not None:
        inside_obs = transmission_mask < 1.0
        intensity[inside_obs] *= transmission_mask[inside_obs]
        xl_blocked = transmission_mask == 0
    return intensity, xl_blocked


def run_simulation(fans_circulares, fans_airfree, fans_ovales, obstacles,
                   img_width, img_height, decay_rate, multiplier, resolution,
                   use_los, progress_callback=None):
    res_map = {"Baja": (100, 100), "Media": (200, 200), "Alta": (400, 400)}
    if resolution in res_map:
        sim_w, sim_h = res_map[resolution]
    else:
        sim_w = max(img_width // 4, 50)
        sim_h = max(img_height // 4, 50)

    scale_x = sim_w / img_width
    scale_y = sim_h / img_height

    yy, xx = np.mgrid[0:sim_h, 0:sim_w]
    grid_x = xx.astype(np.float32)
    grid_y = yy.astype(np.float32)

    total_fans = len(fans_circulares) + len(fans_airfree) + len(fans_ovales)
    total_intensity = np.zeros((sim_h, sim_w), dtype=np.float32)
    fan_idx = 0

    # xl_blocked_all: only True where ALL fans are blocked (intersection → shadow)
    xl_blocked_all = (
        np.ones((sim_h, sim_w), dtype=bool) if total_fans > 0
        else np.zeros((sim_h, sim_w), dtype=bool)
    )

    # Scale obstacles to simulation resolution
    scaled_obstacles = []
    for obs in obstacles:
        pts = (obs["points"] * np.array([scale_x, scale_y])).astype(np.int32)
        scaled_obstacles.append({
            "points": pts,
            "transmission": obs["transmission"],
            "size": obs["size"],
        })

    transmission_mask = build_transmission_mask(scaled_obstacles, sim_h, sim_w)
    has_xl = any(o["transmission"] == 0 for o in scaled_obstacles)

    obstacle_mask_full = np.ones((sim_h, sim_w), dtype=np.uint8)
    obstacle_mask_full[transmission_mask == 0] = 0

    # --- Circular ceiling fans ---
    for fan in fans_circulares:
        sf = {
            "x": fan["x"] * scale_x,
            "y": fan["y"] * scale_y,
            "r": fan["r"] * max(scale_x, scale_y),
        }
        intensity = compute_circular_fan_intensity(sf, grid_x, grid_y, decay_rate, multiplier)
        intensity, fan_xl = _apply_los(sf["x"], sf["y"], intensity, sim_h, sim_w,
                                       obstacles, obstacle_mask_full, scaled_obstacles, use_los,
                                       transmission_mask=transmission_mask)
        xl_blocked_all &= fan_xl
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    # --- AirFree pedestal fans (elliptical model) ---
    for fan in fans_airfree:
        flow_angle_rad = math.radians(fan.get("flow_angle", 0))
        rect_angle = math.radians(fan.get("angle", 0))
        angle_diff = flow_angle_rad - rect_angle
        cos_d = math.cos(angle_diff)
        sin_d = math.sin(angle_diff)

        sf = {
            "x": fan["x"] * scale_x,
            "y": fan["y"] * scale_y,
            "half_w": fan["half_w"] * scale_x,
            "half_h": fan["half_h"] * scale_y,
            "angle": fan.get("angle", 0),
            "flow_angle": fan.get("flow_angle", 0),
        }

        hw, hh = sf["half_w"], sf["half_h"]
        u_extent = hw * abs(cos_d) + hh * abs(sin_d)

        # LOS origin: center of the back face
        Dx = math.cos(flow_angle_rad)
        Dy = math.sin(flow_angle_rad)
        los_x = sf["x"] - u_extent * Dx
        los_y = sf["y"] - u_extent * Dy

        intensity = compute_airfree_fan_intensity(sf, grid_x, grid_y, decay_rate, multiplier)
        intensity, fan_xl = _apply_los(los_x, los_y, intensity, sim_h, sim_w,
                                       obstacles, obstacle_mask_full, scaled_obstacles, use_los,
                                       transmission_mask=transmission_mask)
        xl_blocked_all &= fan_xl
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    # --- Oval fans (ellipses drawn directly) ---
    for fan in fans_ovales:
        sf = {
            "x": fan["x"] * scale_x,
            "y": fan["y"] * scale_y,
            "rx": fan["rx"] * scale_x,
            "ry": fan["ry"] * scale_y,
            "angle": fan.get("angle", 0),
        }
        intensity = compute_oval_fan_intensity(sf, grid_x, grid_y, decay_rate, multiplier)
        intensity, fan_xl = _apply_los(sf["x"], sf["y"], intensity, sim_h, sim_w,
                                       obstacles, obstacle_mask_full, scaled_obstacles, use_los,
                                       transmission_mask=transmission_mask)
        xl_blocked_all &= fan_xl
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    # Zero out obstacle interiors and apply partial transmission
    total_intensity[obstacle_mask_full == 0] = 0
    partial_obs = (transmission_mask > 0) & (transmission_mask < 1.0)
    total_intensity[partial_obs] *= transmission_mask[partial_obs]

    xl_shadow = xl_blocked_all & has_xl

    return total_intensity, sim_w, sim_h, xl_shadow
