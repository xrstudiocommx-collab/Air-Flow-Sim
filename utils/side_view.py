import numpy as np
import math
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, Rectangle, FancyArrow, Polygon
import matplotlib.patheffects as pe

# Thermographic inverse palette (scale 0–100):
#   0   = intense red  (#FF0000) → ambient temperature (no cooling effect)
#   100 = navy blue    (#000080) → maximum cold air intensity
CMAP_COLD_AIR = LinearSegmentedColormap.from_list(
    "cold_air_thermo",
    [
        "#FF0000",  # intense red – 0   (ambient temperature, lowest intensity)
        "#FFA500",  # orange      – ~20 (slightly cooler)
        "#FFFF00",  # yellow      – ~40 (transitioning)
        "#FFFFFF",  # white       – ~60 (mixing zone)
        "#4169E1",  # royal blue  – ~80 (cool air)
        "#000080",  # navy blue   – 100 (maximum cold flow, highest intensity)
    ],
    N=256,
)

SIDE_VIEW_HEIGHT_PX = 300


def run_side_view_simulation(
    fans_circ, fans_airfree, fans_oval,
    img_width, ceiling_height_m, pedestal_height_m,
    decay_rate, multiplier, resolution,
):
    res_map = {"Baja": 100, "Media": 200, "Alta": 400}
    sim_w = res_map.get(resolution, 200)
    sim_h = SIDE_VIEW_HEIGHT_PX

    scale_x = sim_w / img_width

    yy, xx = np.mgrid[0:sim_h, 0:sim_w]
    grid_x = xx.astype(np.float32)
    grid_y = yy.astype(np.float32)

    total_intensity = np.zeros((sim_h, sim_w), dtype=np.float32)

    ceiling_px = 0.0
    floor_px = float(sim_h)
    pedestal_y_px = floor_px - (pedestal_height_m / ceiling_height_m) * sim_h

    for fan in fans_circ:
        fan_x_px = fan["x"] * scale_x
        fan_y_px = ceiling_px
        radius_px = fan.get("r", 20) * scale_x

        sigma_base = radius_px * 0.8
        d_y = grid_y - fan_y_px
        d_y = np.maximum(d_y, 0)
        d_x = grid_x - fan_x_px
        sigma = sigma_base + d_y * 0.3
        intensity = multiplier * np.exp(-decay_rate * d_y * 0.15) * np.exp(
            -(d_x ** 2) / (2.0 * sigma ** 2)
        )
        intensity[grid_y < fan_y_px] = 0
        total_intensity += intensity

    for fan in fans_airfree:
        fan_x_px = fan["x"] * scale_x
        fan_y_px = pedestal_y_px

        flow_angle_deg = fan.get("flow_angle", 0)
        flow_angle_rad = math.radians(flow_angle_deg)
        dx_dir = math.cos(flow_angle_rad)

        hw = fan.get("half_w", 10) * scale_x
        hh = fan.get("half_h", 10) * scale_x
        fan_height_px = max(hh, hw) * 0.5

        sigma_v = fan_height_px * 0.8
        d_x = (grid_x - fan_x_px) * np.sign(dx_dir) if abs(dx_dir) > 0.01 else (grid_x - fan_x_px)
        d_v = grid_y - fan_y_px
        sigma_h = sigma_v + np.abs(d_x) * 0.15

        if abs(dx_dir) > 0.01:
            forward = d_x * np.sign(dx_dir)
            intensity = multiplier * np.exp(-decay_rate * np.abs(d_x) * 0.12) * np.exp(
                -(d_v ** 2) / (2.0 * sigma_h ** 2)
            )
            intensity[forward < 0] = 0
        else:
            dist = np.sqrt(d_x ** 2 + d_v ** 2)
            intensity = multiplier * np.exp(-decay_rate * dist * 0.12)

        total_intensity += intensity

    for fan in fans_oval:
        fan_x_px = fan["x"] * scale_x
        fan_y_px = ceiling_px
        rx = fan.get("rx", 20) * scale_x

        sigma_base = rx * 0.8
        d_y = grid_y - fan_y_px
        d_y = np.maximum(d_y, 0)
        d_x = grid_x - fan_x_px
        sigma = sigma_base + d_y * 0.3
        intensity = multiplier * np.exp(-decay_rate * d_y * 0.15) * np.exp(
            -(d_x ** 2) / (2.0 * sigma ** 2)
        )
        intensity[grid_y < fan_y_px] = 0
        total_intensity += intensity

    return total_intensity, sim_w, sim_h


def _draw_ceiling_fan_jet(ax, fx, fan_y, sim_h, radius_scaled, jet_color="#0066CC"):
    jet_length = sim_h * 0.55
    spread_top = radius_scaled * 0.4
    spread_bot = radius_scaled * 1.8

    jet_top_y = fan_y + 2
    jet_bot_y = fan_y + jet_length

    n_layers = 8
    for i in range(n_layers):
        t0 = i / n_layers
        t1 = (i + 1) / n_layers
        y0 = jet_top_y + t0 * (jet_bot_y - jet_top_y)
        y1 = jet_top_y + t1 * (jet_bot_y - jet_top_y)
        w0 = spread_top + t0 * (spread_bot - spread_top)
        w1 = spread_top + t1 * (spread_bot - spread_top)
        alpha = 0.45 * (1 - t0 * 0.7)

        verts = [
            (fx - w0, y0),
            (fx + w0, y0),
            (fx + w1, y1),
            (fx - w1, y1),
        ]
        poly = Polygon(verts, closed=True, facecolor=jet_color, alpha=alpha,
                        edgecolor="none", zorder=3)
        ax.add_patch(poly)

    arrow = FancyArrow(fx, fan_y + 4, 0, jet_length * 0.5,
                       width=spread_top * 0.6, head_width=spread_top * 1.2,
                       head_length=jet_length * 0.08,
                       fc="#00BBFF", ec="white", lw=1, alpha=0.7, zorder=4)
    ax.add_patch(arrow)


def _draw_pedestal_fan_jet(ax, fx, fy, dx_dir, sim_w, fan_hw, jet_color="#0066CC"):
    jet_length = sim_w * 0.18
    spread_top = fan_hw * 0.25
    spread_bot = fan_hw * 1.2
    direction = 1 if dx_dir >= 0 else -1

    n_layers = 8
    for i in range(n_layers):
        t0 = i / n_layers
        t1 = (i + 1) / n_layers
        x0 = fx + direction * t0 * jet_length
        x1 = fx + direction * t1 * jet_length
        w0 = spread_top + t0 * (spread_bot - spread_top)
        w1 = spread_top + t1 * (spread_bot - spread_top)
        alpha = 0.45 * (1 - t0 * 0.7)

        verts = [
            (x0, fy - w0),
            (x0, fy + w0),
            (x1, fy + w1),
            (x1, fy - w1),
        ]
        poly = Polygon(verts, closed=True, facecolor=jet_color, alpha=alpha,
                        edgecolor="none", zorder=3)
        ax.add_patch(poly)

    arrow = FancyArrow(fx, fy, direction * jet_length * 0.5, 0,
                       width=spread_top * 0.5, head_width=spread_top * 1.0,
                       head_length=jet_length * 0.08,
                       fc="#00BBFF", ec="white", lw=1, alpha=0.7, zorder=4)
    ax.add_patch(arrow)


def render_side_view_figure(
    total_intensity, sim_w, sim_h,
    fans_circ, fans_airfree, fans_oval,
    img_width, ceiling_height_m, pedestal_height_m,
    heatmap_alpha,
    ambient_temp=30,
    sim_date=None,
    sim_time=None,
    thermal_change=22,
    air_speed="1 m/s",
    fig_bg="#1E1E2E",
    fig_fg="#E0E0E0",
):
    scale_x = sim_w / img_width
    floor_px = float(sim_h)
    pedestal_y_px = floor_px - (pedestal_height_m / ceiling_height_m) * sim_h

    fig, ax = plt.subplots(figsize=(10, 4))
    _is_light = fig_bg.upper().startswith("#F")
    _ax_bg = "#E8EAF0" if _is_light else "#2A2A3E"
    _line_color = fig_fg

    fig.patch.set_facecolor(fig_bg)
    ax.set_facecolor(_ax_bg)

    ax.axhline(y=0, color=_line_color, linewidth=2, linestyle="-")
    ax.axhline(y=sim_h, color="#8B4513", linewidth=3, linestyle="-")

    ax.fill_between([0, sim_w], sim_h, sim_h + 10, color="#8B4513", alpha=0.5)
    ax.fill_between([0, sim_w], -10, 0, color="#666666", alpha=0.5)

    display_intensity = total_intensity.copy()
    # Scale intensities so that the typical maximum maps to ~100 (0–100 scale)
    # 0 = ambient temperature (intense red), 100 = maximum cold air (navy blue)
    valid_vals = total_intensity[total_intensity > 0]
    raw_max = float(np.max(valid_vals)) if len(valid_vals) > 0 else 1.0
    raw_max = max(raw_max, 0.01)
    scale_factor = 100.0 / raw_max
    display_intensity = display_intensity * scale_factor
    display_intensity[total_intensity == 0] = np.nan
    masked = np.ma.masked_invalid(display_intensity)

    im = ax.imshow(
        masked, cmap=CMAP_COLD_AIR, alpha=heatmap_alpha,
        extent=[0, sim_w, sim_h, 0], vmin=0, vmax=100,
        aspect="auto",
    )

    for fan in fans_circ:
        fx = fan["x"] * scale_x
        r_scaled = max(fan.get("r", 10) * scale_x, 6)
        r_draw = max(r_scaled * 0.3, 4)

        _draw_ceiling_fan_jet(ax, fx, 2 + r_draw * 2, sim_h, r_scaled)

        circ = Circle((fx, 2 + r_draw), r_draw, color="#FF6600", ec=fig_fg, lw=1.5, zorder=8)
        ax.add_patch(circ)
        ax.text(fx, -3, "Techo",
                ha="center", va="bottom", fontsize=6, color=fig_fg, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#FF6600", alpha=0.8),
                zorder=9)

    for fan in fans_airfree:
        fx = fan["x"] * scale_x
        fy = pedestal_y_px
        hw = max(fan.get("half_w", 8) * scale_x * 0.3, 3)
        hh = max(fan.get("half_h", 8) * scale_x * 0.3, 5)

        flow_angle_deg = fan.get("flow_angle", 0)
        dx_dir = math.cos(math.radians(flow_angle_deg))

        fan_hw_full = max(fan.get("half_w", 8) * scale_x, 6)
        _draw_pedestal_fan_jet(ax, fx, fy, dx_dir, sim_w, fan_hw_full)

        rect = Rectangle((fx - hw, fy - hh), hw * 2, hh * 2,
                          color="#00AAFF", ec=fig_fg, lw=1.5, zorder=8)
        ax.add_patch(rect)
        ax.text(fx, fy - hh - 4, "Pedestal",
                ha="center", va="bottom", fontsize=6, color=fig_fg, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#00AAFF", alpha=0.8),
                zorder=9)

    for fan in fans_oval:
        fx = fan["x"] * scale_x
        r_scaled = max(fan.get("rx", 10) * scale_x, 6)
        r_draw = max(r_scaled * 0.3, 4)

        _draw_ceiling_fan_jet(ax, fx, 2 + r_draw * 2, sim_h, r_scaled)

        circ = Circle((fx, 2 + r_draw), r_draw, color="#FF6600", ec=fig_fg, lw=1.5, zorder=8)
        ax.add_patch(circ)

    n_ticks = 6
    y_ticks_px = np.linspace(0, sim_h, n_ticks)
    y_labels_m = [f"{ceiling_height_m - (t / sim_h) * ceiling_height_m:.1f} m" for t in y_ticks_px]
    ax.set_yticks(y_ticks_px)
    ax.set_yticklabels(y_labels_m, fontsize=8, color=fig_fg)

    n_xticks = 8
    x_ticks_px = np.linspace(0, sim_w, n_xticks)
    x_labels = [f"{int(t / scale_x)}" for t in x_ticks_px]
    ax.set_xticks(x_ticks_px)
    ax.set_xticklabels(x_labels, fontsize=8, color=fig_fg)

    ax.set_xlabel("Distancia X (px)", fontsize=9, color=fig_fg)
    ax.set_ylabel("Altura (m)", fontsize=9, color=fig_fg)
    ax.set_title("Vista Lateral (Elevación) — Flujo de Aire", fontsize=11, color=fig_fg, pad=10)

    ax.set_xlim(0, sim_w)
    ax.set_ylim(sim_h + 5, -5)
    ax.tick_params(colors=fig_fg)
    for spine in ax.spines.values():
        spine.set_color(fig_fg)
        spine.set_linewidth(0.5)

    # ── Ceiling-height indicator (LEFT side) ─────────────────────────────────
    # Vertical double-headed arrow at 4% from the left edge, label to its right.
    arrow_x = sim_w * 0.04
    ax.annotate(
        "", xy=(arrow_x, sim_h), xytext=(arrow_x, 0),
        arrowprops=dict(
            arrowstyle="<->", color=fig_fg, lw=1.5,
            shrinkA=0, shrinkB=0,
        ),
        zorder=10,
    )
    _badge_bg = "#1a1a2e" if not _is_light else "#FFFFFF"
    ax.text(
        arrow_x + sim_w * 0.01, sim_h / 2,
        f"Altura:\n{ceiling_height_m:.1f} m",
        ha="left", va="center", fontsize=7, color=fig_fg, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.25", facecolor=_badge_bg, alpha=0.75),
        zorder=11,
    )

    # ── Dynamic colorbar — identical to the top-view (Vista Superior) ─────────
    # 0 (red) = Temp. Ambiente, 100 (blue) = Sensación térmica calculada
    # Temperature labels appear on BOTH sides of the colour strip.
    cbar = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    if thermal_change < ambient_temp:
        cbar_ticks = [0, 25, 50, 75, 100]
        cbar_labels = [
            f"{ambient_temp - t / 100.0 * (ambient_temp - thermal_change):.1f} °C"
            for t in cbar_ticks
        ]
        cbar.set_ticks(cbar_ticks)
        cbar.set_ticklabels(cbar_labels)
        cbar.ax.yaxis.set_ticks_position("right")
        cbar.ax.tick_params(
            which="both",
            left=False, right=True,
            labelleft=False, labelright=True,
            colors=fig_fg, labelsize=7,
        )
        cbar.set_label(
            f"Temperatura  ▼ {ambient_temp}°C (ambiente) → {thermal_change}°C (sens. térmica) ▲",
            fontsize=7, color=fig_fg,
        )
    else:
        cbar.ax.tick_params(colors=fig_fg, labelsize=7)
        cbar.set_label(
            "Sensación térmica ≥ Temp. Ambiente — sin diferencia de enfriamiento",
            fontsize=7, color="orange",
        )
    cbar.outline.set_edgecolor(fig_fg)

    # Contextual annotations: ambient temp, date/time, thermal sensation
    from datetime import date as _date, time as _time
    fecha_str = sim_date.strftime("%Y-%m-%d") if sim_date is not None else _date.today().strftime("%Y-%m-%d")
    hora_str = sim_time.strftime("%H:%M") if sim_time is not None else _time(0, 0).strftime("%H:%M")
    annotation_text = (
        f"Temp. Ambiente: {ambient_temp} °C    "
        f"Fecha: {fecha_str} | Hora: {hora_str}    "
        f"Sensación térmica: {thermal_change} °C a {air_speed}"
    )
    fig.text(
        0.5, 0.01, annotation_text,
        ha="center", va="bottom", fontsize=7, color=fig_fg,
        bbox=dict(boxstyle="round,pad=0.3", facecolor=_badge_bg, alpha=0.75),
    )

    plt.tight_layout()
    return fig
