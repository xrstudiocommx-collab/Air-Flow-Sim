import numpy as np
import cv2
import math


def compute_circular_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier):
    fx, fy = fan["x"], fan["y"]
    radius = fan.get("r", 0)
    dist = np.sqrt((grid_x - fx) ** 2 + (grid_y - fy) ** 2)

    intensity = np.zeros_like(dist)
    interior = dist <= radius
    intensity[interior] = multiplier
    exterior = dist > radius
    intensity[exterior] = multiplier * np.exp(-(dist[exterior] - radius) * decay_rate)

    return intensity


def compute_airfree_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier):
    """
    AirFree pedestal fan with explicit flow direction angle.

    The rectangle body is always filled with max intensity. Outside the body:
      - Points in the "back half-space" (behind the back face in flow direction): intensity = 0.
      - All other exterior points: exponential decay from the front face segment.

    Coordinate system (flow-aligned, centered at fan center):
      u = projection along flow direction D
      v = projection perpendicular to D

    The rectangle's bounding box in flow coords gives:
      u_extent  = front face distance from center (positive)
      u_back    = back face distance from center (negative = -u_extent)
      v_extent  = lateral half-width of the front face segment

    The "front face segment" is the line u = u_extent, v in [-v_extent, +v_extent].
    Distance to it gives a radial decay from that segment in all forward directions.
    """
    cx, cy = fan["x"], fan["y"]
    half_w = max(fan["half_w"], 1)
    half_h = max(fan["half_h"], 1)
    rect_angle = math.radians(fan.get("angle", 0))
    flow_angle_rad = math.radians(fan.get("flow_angle", 0))

    # Flow unit vector and its perpendicular
    Dx = math.cos(flow_angle_rad)
    Dy = math.sin(flow_angle_rad)
    Px = -Dy   # perpendicular (90° CCW)
    Py = Dx

    # Grid in flow-aligned coords centered at fan
    gx = grid_x - cx
    gy = grid_y - cy
    u = gx * Dx + gy * Dy   # along flow
    v = gx * Px + gy * Py   # perpendicular

    # Rectangle bounding box extents in flow-aligned coords.
    # angle_diff is angle from rectangle local x-axis to flow direction.
    angle_diff = flow_angle_rad - rect_angle
    cos_d = math.cos(angle_diff)
    sin_d = math.sin(angle_diff)
    u_extent = half_w * abs(cos_d) + half_h * abs(sin_d)  # front half-extent along flow
    v_extent = half_w * abs(sin_d) + half_h * abs(cos_d)  # lateral half-extent

    # Check whether points lie inside the rectangle (use rect-local coords)
    cos_r = math.cos(-rect_angle)
    sin_r = math.sin(-rect_angle)
    x_loc = gx * cos_r - gy * sin_r
    y_loc = gx * sin_r + gy * cos_r
    inside_rect = (np.abs(x_loc) <= half_w) & (np.abs(y_loc) <= half_h)

    # Distance from each grid point to the front face segment.
    # Front face segment: u = u_extent, v in [-v_extent, +v_extent].
    v_clamped = np.clip(v, -v_extent, v_extent)
    dist_to_front = np.sqrt((u - u_extent) ** 2 + (v - v_clamped) ** 2)

    intensity = np.zeros_like(u, dtype=np.float32)

    # Interior: constant max intensity
    intensity[inside_rect] = multiplier

    # Exterior points that are NOT behind the back face (-u_extent)
    exterior_forward = ~inside_rect & (u >= -u_extent)
    intensity[exterior_forward] = multiplier * np.exp(
        -dist_to_front[exterior_forward] * decay_rate
    )
    # Points with u < -u_extent (behind back face) stay at 0

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

    intensity = np.zeros_like(norm_dist)
    interior = norm_dist <= 1.0
    intensity[interior] = multiplier
    exterior = norm_dist > 1.0
    intensity[exterior] = multiplier * np.exp(-(norm_dist[exterior] - 1.0) * decay_rate * max(a, b))

    # Smooth directional bias via sigmoid on cosine of angle (avoids hard edge)
    angle = np.arctan2(dy_rot, dx_rot)
    cos_angle = np.cos(angle)
    smoothing = 4.0
    directional = 0.3 + 0.7 / (1.0 + np.exp(-smoothing * cos_angle))
    intensity *= directional

    return intensity


def build_obstacle_mask(obstacles, height, width):
    mask = np.ones((height, width), dtype=np.uint8)
    for obs in obstacles:
        pts = obs["points"].copy()
        if pts.shape[0] >= 3:
            cv2.fillPoly(mask, [pts], 0)
    return mask


def compute_visibility(fan_x, fan_y, height, width, obstacle_mask, num_samples=64):
    visibility = np.ones((height, width), dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    dx = xx.astype(np.float32) - fan_x
    dy = yy.astype(np.float32) - fan_y

    for i in range(1, num_samples + 1):
        t = i / num_samples
        sx = np.clip((fan_x + t * dx).astype(np.int32), 0, width - 1)
        sy = np.clip((fan_y + t * dy).astype(np.int32), 0, height - 1)
        hit = obstacle_mask[sy, sx] == 0
        visibility[hit] = 0

    return visibility


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


def _apply_los(fan_x, fan_y, intensity, sim_h, sim_w, obstacles, obstacle_mask_full,
               scaled_obstacles, use_los, transmission_mask=None, num_samples=48):
    xl_blocked = np.zeros((sim_h, sim_w), dtype=bool)
    if use_los and len(obstacles) > 0:
        if transmission_mask is not None:
            att = compute_visibility_with_transmission(
                fan_x, fan_y, sim_h, sim_w, transmission_mask, num_samples=num_samples
            )
            inside_obs = transmission_mask < 1.0
            att[inside_obs] = np.minimum(att[inside_obs], transmission_mask[inside_obs])
            xl_blocked = att == 0
            intensity *= att
        else:
            vis = compute_visibility(fan_x, fan_y, sim_h, sim_w, obstacle_mask_full, num_samples=num_samples)
            xl_blocked = vis == 0
            intensity *= vis
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

    xl_blocked_all = np.ones((sim_h, sim_w), dtype=bool) if total_fans > 0 else np.zeros((sim_h, sim_w), dtype=bool)

    scaled_obstacles = []
    for obs in obstacles:
        pts = (obs["points"] * np.array([scale_x, scale_y])).astype(np.int32)
        scaled_obs = {"points": pts, "transmission": obs["transmission"], "size": obs["size"]}
        scaled_obstacles.append(scaled_obs)

    transmission_mask = build_transmission_mask(scaled_obstacles, sim_h, sim_w)
    has_xl = any(o["transmission"] == 0 for o in scaled_obstacles)

    obstacle_mask_full = np.ones((sim_h, sim_w), dtype=np.uint8)
    obstacle_mask_full[transmission_mask == 0] = 0

    # --- Circular ceiling fans ---
    for fan in fans_circulares:
        scaled_fan = {"x": fan["x"] * scale_x, "y": fan["y"] * scale_y,
                      "r": fan["r"] * max(scale_x, scale_y)}
        intensity = compute_circular_fan_intensity(scaled_fan, grid_x, grid_y, decay_rate, multiplier)
        intensity, fan_xl = _apply_los(scaled_fan["x"], scaled_fan["y"], intensity, sim_h, sim_w,
                                       obstacles, obstacle_mask_full, scaled_obstacles, use_los,
                                       transmission_mask=transmission_mask)
        xl_blocked_all &= fan_xl
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    # --- AirFree pedestal fans (rectangles with explicit flow direction) ---
    for fan in fans_airfree:
        flow_angle_rad = math.radians(fan.get("flow_angle", 0))
        rect_angle = math.radians(fan.get("angle", 0))
        angle_diff = flow_angle_rad - rect_angle
        cos_d = math.cos(angle_diff)
        sin_d = math.sin(angle_diff)

        scaled_fan = {
            "x": fan["x"] * scale_x,
            "y": fan["y"] * scale_y,
            "half_w": fan["half_w"] * scale_x,
            "half_h": fan["half_h"] * scale_y,
            "angle": fan.get("angle", 0),
            "flow_angle": fan.get("flow_angle", 0),
        }

        # Bounding extent along flow axis (for back face position)
        hw = scaled_fan["half_w"]
        hh = scaled_fan["half_h"]
        u_extent = hw * abs(cos_d) + hh * abs(sin_d)

        # LOS origin: center of the back face in world coords
        Dx = math.cos(flow_angle_rad)
        Dy = math.sin(flow_angle_rad)
        los_x = scaled_fan["x"] - u_extent * Dx
        los_y = scaled_fan["y"] - u_extent * Dy

        intensity = compute_airfree_fan_intensity(scaled_fan, grid_x, grid_y, decay_rate, multiplier)
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
        scaled_fan = {
            "x": fan["x"] * scale_x,
            "y": fan["y"] * scale_y,
            "rx": fan["rx"] * scale_x,
            "ry": fan["ry"] * scale_y,
            "angle": fan.get("angle", 0),
        }
        intensity = compute_oval_fan_intensity(scaled_fan, grid_x, grid_y, decay_rate, multiplier)
        intensity, fan_xl = _apply_los(scaled_fan["x"], scaled_fan["y"], intensity, sim_h, sim_w,
                                       obstacles, obstacle_mask_full, scaled_obstacles, use_los,
                                       transmission_mask=transmission_mask)
        xl_blocked_all &= fan_xl
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    total_intensity[obstacle_mask_full == 0] = 0
    partial_obs = (transmission_mask > 0) & (transmission_mask < 1.0)
    total_intensity[partial_obs] *= transmission_mask[partial_obs]

    xl_shadow = xl_blocked_all & has_xl

    return total_intensity, sim_w, sim_h, xl_shadow
