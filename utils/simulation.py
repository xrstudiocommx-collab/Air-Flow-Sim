import numpy as np
import cv2
import math


def compute_circular_fan_intensity(fan, grid_x, grid_y, decay_rate, multiplier):
    fx, fy = fan["x"], fan["y"]
    dist = np.sqrt((grid_x - fx) ** 2 + (grid_y - fy) ** 2)
    intensity = multiplier * np.exp(-dist * decay_rate)
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

    norm_dist_sq = (dx_rot / a) ** 2 + (dy_rot / b) ** 2
    intensity = multiplier * np.exp(-np.sqrt(norm_dist_sq) * decay_rate)

    forward = dx_rot > 0
    directional = np.where(forward, 1.0, 0.3)
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


def compute_visibility_with_transmission(fan_x, fan_y, height, width, obstacles, num_samples=64):
    attenuation = np.ones((height, width), dtype=np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    dx = xx.astype(np.float32) - fan_x
    dy = yy.astype(np.float32) - fan_y

    for obs in obstacles:
        transmission = obs["transmission"]
        pts = obs["points"]
        obs_mask = np.zeros((height, width), dtype=np.uint8)
        if pts.shape[0] >= 3:
            cv2.fillPoly(obs_mask, [pts], 1)

        ray_hits = np.zeros((height, width), dtype=bool)
        for i in range(1, num_samples + 1):
            t = i / num_samples
            sx = np.clip((fan_x + t * dx).astype(np.int32), 0, width - 1)
            sy = np.clip((fan_y + t * dy).astype(np.int32), 0, height - 1)
            ray_hits |= (obs_mask[sy, sx] == 1)

        if transmission == 0:
            attenuation[ray_hits] = 0
        else:
            attenuation[ray_hits] = np.minimum(attenuation[ray_hits], transmission)

    return attenuation


def _apply_los(fan_x, fan_y, intensity, sim_h, sim_w, obstacles, obstacle_mask_full,
               scaled_obstacles, use_los, num_samples=48):
    if use_los and len(obstacles) > 0:
        has_partial = any(o["transmission"] > 0 for o in scaled_obstacles)
        if has_partial:
            att = compute_visibility_with_transmission(
                fan_x, fan_y, sim_h, sim_w, scaled_obstacles, num_samples=num_samples
            )
            intensity *= att
        else:
            vis = compute_visibility(fan_x, fan_y, sim_h, sim_w, obstacle_mask_full, num_samples=num_samples)
            intensity *= vis
    else:
        intensity *= obstacle_mask_full
    return intensity


def run_simulation(fans_circulares, fans_ovales, obstacles, img_width, img_height,
                   decay_rate, multiplier, resolution, use_los, progress_callback=None):
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

    total_intensity = np.zeros((sim_h, sim_w), dtype=np.float32)
    total_fans = len(fans_circulares) + len(fans_ovales)
    fan_idx = 0

    obstacle_mask_full = np.ones((sim_h, sim_w), dtype=np.uint8)
    scaled_obstacles = []
    for obs in obstacles:
        pts = (obs["points"] * np.array([scale_x, scale_y])).astype(np.int32)
        if pts.shape[0] >= 3:
            cv2.fillPoly(obstacle_mask_full, [pts], 0)
        scaled_obs = {"points": pts, "transmission": obs["transmission"], "size": obs["size"]}
        scaled_obstacles.append(scaled_obs)

    for fan in fans_circulares:
        scaled_fan = {"x": fan["x"] * scale_x, "y": fan["y"] * scale_y, "r": fan["r"]}
        intensity = compute_circular_fan_intensity(scaled_fan, grid_x, grid_y, decay_rate, multiplier)
        intensity = _apply_los(scaled_fan["x"], scaled_fan["y"], intensity, sim_h, sim_w,
                               obstacles, obstacle_mask_full, scaled_obstacles, use_los)
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    for fan in fans_ovales:
        scaled_fan = {
            "x": fan["x"] * scale_x,
            "y": fan["y"] * scale_y,
            "rx": fan["rx"] * scale_x,
            "ry": fan["ry"] * scale_y,
            "angle": fan.get("angle", 0),
        }
        intensity = compute_oval_fan_intensity(scaled_fan, grid_x, grid_y, decay_rate, multiplier)
        intensity = _apply_los(scaled_fan["x"], scaled_fan["y"], intensity, sim_h, sim_w,
                               obstacles, obstacle_mask_full, scaled_obstacles, use_los)
        total_intensity += intensity
        fan_idx += 1
        if progress_callback:
            progress_callback(fan_idx / max(total_fans, 1))

    total_intensity[obstacle_mask_full == 0] = 0

    return total_intensity, sim_w, sim_h
