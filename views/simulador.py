import streamlit as st
import numpy as np
import math
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap
import io
import os
import pandas as pd
from datetime import datetime
from streamlit_drawable_canvas import st_canvas

# Thermographic inverse palette (scale 0–100):
#   0   = intense red  (#FF0000) → ambient temperature (no cooling effect)
#   100 = navy blue    (#000080) → maximum cold air intensity
CMAP_COLD_AIR = LinearSegmentedColormap.from_list(
    "cold_air_thermo",
    [
        "#FF0000",  # intense red  – 0   (ambient temperature, lowest intensity)
        "#FFA500",  # orange       – ~20 (slightly cooler)
        "#FFFF00",  # yellow       – ~40 (transitioning)
        "#FFFFFF",  # white        – ~60 (mixing zone)
        "#4169E1",  # royal blue   – ~80 (cool air)
        "#000080",  # navy blue    – 100 (maximum cold flow, highest intensity)
    ],
    N=256,
)

from utils.canvas_utils import parse_canvas_objects, SIZE_TRANSMISSION
from utils.simulation import run_simulation
from utils.side_view import run_side_view_simulation, render_side_view_figure
from utils.streamlines import compute_streamlines, render_streamlines_figure
from utils.db import create_proyecto
from utils.auth import get_current_user

# ---------------------------------------------------------------------------
# Thermal sensation lookup table — Kale Fans América by XR Studio
# Source: effective temperature table by ambient temp (°C) and air speed (m/s)
# Structure: {speed_ms: {ambient_temp_int: effective_temp_float}}
# ---------------------------------------------------------------------------
_THERMAL_TABLE = {
    # Source: Kale Fans América by XR Studio — effective temperature table
    # Only the three speeds selectable by the user are included.
    1.0: {20:14.0,21:15.0,22:16.5,23:18.0,24:19.0,25:20.9,26:22.0,27:23.0,28:24.5,29:25.5,30:27.0,31:28.0,32:29.2,33:30.7,34:31.9,35:34.0,36:34.5,37:36.9,38:37.0,39:39.3,40:40.4,41:41.4,42:42.5,43:43.6,44:44.6,45:45.7},
    2.0: {20:10.0,21:12.0,22:13.2,23:15.0,24:16.3,25:18.0,26:19.3,27:20.9,28:22.2,29:23.8,30:25.2,31:26.0,32:27.8,33:29.2,34:31.0,35:33.0,36:34.5,37:36.0,38:37.0,39:39.6,40:40.7,41:41.8,42:43.0,43:44.1,44:45.3,45:46.4},
    3.0: {20:7.5, 21:9.0, 22:10.5,23:12.8,24:14.2,25:16.0,26:17.0,27:19.0,28:20.8,29:22.2,30:23.8,31:25.5,32:26.9,33:28.4,34:30.0,35:32.0,36:34.5,37:35.0,38:37.0,39:39.8,40:41.0,41:42.3,42:43.5,43:44.7,44:45.9,45:47.1},
}
_THERMAL_SPEEDS = sorted(_THERMAL_TABLE.keys())


def calcular_sensacion_termica(temp_ambiente: float, velocidad: float) -> float:
    """Return the effective thermal sensation temperature using bilinear interpolation
    on the Kale Fans América table.  Both temp_ambiente and velocidad are clamped to
    the table's supported range.
    """
    # --- clamp speed to table bounds ---
    v_lo = _THERMAL_SPEEDS[0]
    v_hi = _THERMAL_SPEEDS[-1]
    velocidad = max(v_lo, min(v_hi, velocidad))

    # --- find bracketing speeds ---
    v_lower = v_lo
    v_upper = v_hi
    for s in _THERMAL_SPEEDS:
        if s <= velocidad:
            v_lower = s
        if s >= velocidad and v_upper == v_hi:
            v_upper = s
            break

    def _interp_at_speed(speed_key: float, t: float) -> float:
        row = _THERMAL_TABLE[speed_key]
        temps = sorted(row.keys())
        t_lo_k = temps[0]
        t_hi_k = temps[-1]
        t = max(t_lo_k, min(t_hi_k, t))
        t_floor = int(t)
        t_ceil = t_floor + 1
        if t_ceil not in row:
            return row.get(t_floor, t)
        frac = t - t_floor
        return row[t_floor] * (1 - frac) + row[t_ceil] * frac

    if v_lower == v_upper:
        return round(_interp_at_speed(v_lower, temp_ambiente), 1)

    eff_lo = _interp_at_speed(v_lower, temp_ambiente)
    eff_hi = _interp_at_speed(v_upper, temp_ambiente)
    v_frac = (velocidad - v_lower) / (v_upper - v_lower)
    return round(eff_lo * (1 - v_frac) + eff_hi * v_frac, 1)


# Internal key → full display name (used in UI selectors)
OBS_DISPLAY_NAMES = {
    "Ch": "Obstáculo Chico",
    "M":  "Obstáculo Mediano",
    "G":  "Obstáculo Grande",
    "XL": "Pared",
}

# Internal key → short map label (shown on heatmap overlay)
OBS_MAP_LABELS = {
    "Ch": "Obj. Ch",
    "M":  "Obj. M",
    "G":  "Obj. G",
    "XL": "Pared",
}


def _init_state():
    if "sim_canvas_key" not in st.session_state:
        st.session_state["sim_canvas_key"] = "sim_canvas"
    if "saved_obstacles" not in st.session_state:
        st.session_state["saved_obstacles"] = []
    if "polygon_points_temp" not in st.session_state:
        st.session_state["polygon_points_temp"] = []
    if "airfree_angles" not in st.session_state:
        st.session_state["airfree_angles"] = {}
    if "saved_fans_raw" not in st.session_state:
        st.session_state["saved_fans_raw"] = []
    if "_prev_canvas_key" not in st.session_state:
        st.session_state["_prev_canvas_key"] = None
    # Flow-limit polygons drawn by the user
    if "flow_limits" not in st.session_state:
        st.session_state["flow_limits"] = []
    if "flow_polygon_points_temp" not in st.session_state:
        st.session_state["flow_polygon_points_temp"] = []


def _build_initial_drawing(w, h, saved_obstacles, saved_fans_raw=None):
    objects = []
    for obs in saved_obstacles:
        pts = obs["points"]
        if len(pts) < 3:
            continue
        min_x = min(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        fabric_pts = [{"x": p[0] - min_x, "y": p[1] - min_y} for p in pts]
        size_label = obs.get("size", "XL")
        color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
        objects.append({
            "type": "polygon",
            "left": min_x,
            "top": min_y,
            "fill": "rgba(255,0,0,0.15)",
            "stroke": color_map.get(size_label, "#FF0000"),
            "strokeWidth": 2,
            "points": fabric_pts,
            "scaleX": 1,
            "scaleY": 1,
            "angle": 0,
            "selectable": False,
            "evented": False,
        })
    if saved_fans_raw:
        for fan_obj in saved_fans_raw:
            objects.append(fan_obj)
    return {"version": "4.4.0", "objects": objects}


def _draw_polygon_preview(bg_image, temp_points, saved_fans_raw=None,
                          saved_obstacles=None, flow_limits=None,
                          temp_flow_points=None, drawing_flow=False):
    overlay = bg_image.copy().convert("RGBA")
    draw_layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(draw_layer)

    if saved_fans_raw:
        for obj in saved_fans_raw:
            obj_type = obj.get("type", "")
            left = obj.get("left", 0)
            top = obj.get("top", 0)
            sx = obj.get("scaleX", 1)
            sy = obj.get("scaleY", 1)
            if obj_type == "circle":
                radius = obj.get("radius", 0)
                cx = left + radius * sx
                cy = top + radius * sy
                r_draw = int(radius * max(sx, sy))
                draw.ellipse(
                    [int(cx - r_draw), int(cy - r_draw), int(cx + r_draw), int(cy + r_draw)],
                    outline="#FF6600", width=2,
                )
                draw.text((int(cx) - 6, int(cy) - 6), "T", fill="#FF6600")
            elif obj_type == "rect":
                w_r = obj.get("width", 0) * sx
                h_r = obj.get("height", 0) * sy
                draw.rectangle(
                    [int(left), int(top), int(left + w_r), int(top + h_r)],
                    outline="#00AAFF", width=2,
                )
                draw.text((int(left + w_r / 2) - 6, int(top + h_r / 2) - 6), "P", fill="#00AAFF")

    if saved_obstacles:
        color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
        for obs in saved_obstacles:
            pts = obs["points"]
            if len(pts) >= 3:
                flat = [(int(p[0]), int(p[1])) for p in pts]
                flat_closed = flat + [flat[0]]
                color = color_map.get(obs.get("size", "XL"), "#FF0000")
                draw.line(flat_closed, fill=color, width=2)

    # Draw saved flow-limit polygons in purple
    if flow_limits:
        for poly_data in flow_limits:
            pts = poly_data.get("points", [])
            if len(pts) >= 3:
                flat = [(int(p[0]), int(p[1])) for p in pts]
                flat_closed = flat + [flat[0]]
                draw.line(flat_closed, fill="#9B59B6", width=2)

    r = 4
    if drawing_flow:
        # Draw the in-progress flow-limit polygon in purple
        fp = temp_flow_points or []
        for px, py in fp:
            draw.ellipse([px - r, py - r, px + r, py + r], fill="#9B59B6", outline="white")
        if len(fp) >= 2:
            flat = [(int(p[0]), int(p[1])) for p in fp]
            draw.line(flat, fill="#9B59B6", width=2)
    else:
        # Draw the in-progress obstacle polygon in red
        for px, py in temp_points:
            draw.ellipse([px - r, py - r, px + r, py + r], fill="red", outline="white")
        if len(temp_points) >= 2:
            flat = [(int(p[0]), int(p[1])) for p in temp_points]
            draw.line(flat, fill="red", width=2)

    overlay = Image.alpha_composite(overlay, draw_layer)
    return overlay


def _draw_fans_on_bg(bg_image, fans_airfree):
    """Overlay direction arrows on the background image for AirFree fans."""
    overlay = bg_image.copy().convert("RGBA")
    arrow_layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(arrow_layer)

    for fan in fans_airfree:
        cx, cy = fan["x"], fan["y"]
        hw = fan["half_w"]
        hh = fan["half_h"]
        rect_angle = math.radians(fan.get("angle", 0))
        flow_angle_rad = math.radians(fan.get("flow_angle", 0))

        # Draw rectangle outline
        cos_r = math.cos(rect_angle)
        sin_r = math.sin(rect_angle)
        corners_local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        corners_world = []
        for lx, ly in corners_local:
            wx = cx + lx * cos_r - ly * sin_r
            wy = cy + lx * sin_r + ly * cos_r
            corners_world.append((int(wx), int(wy)))
        draw.polygon(corners_world, outline=(0, 170, 255, 220))

        # Compute flow direction extents
        angle_diff = flow_angle_rad - rect_angle
        u_extent = hw * abs(math.cos(angle_diff)) + hh * abs(math.sin(angle_diff))
        Dx = math.cos(flow_angle_rad)
        Dy = math.sin(flow_angle_rad)

        # Arrow: from back face center to a point beyond the front face
        back_x = cx - u_extent * Dx
        back_y = cy - u_extent * Dy
        front_x = cx + u_extent * Dx
        front_y = cy + u_extent * Dy
        tip_x = cx + (u_extent + min(hw, hh) * 0.8) * Dx
        tip_y = cy + (u_extent + min(hw, hh) * 0.8) * Dy

        # Arrow shaft
        draw.line([(int(back_x), int(back_y)), (int(tip_x), int(tip_y))],
                  fill=(255, 255, 255, 230), width=3)

        # Arrowhead (triangle)
        head_len = max(10, int(min(hw, hh) * 0.5))
        perp_x = -Dy
        perp_y = Dx
        tip = (int(tip_x), int(tip_y))
        base1 = (int(tip_x - head_len * Dx + head_len * 0.4 * perp_x),
                 int(tip_y - head_len * Dy + head_len * 0.4 * perp_y))
        base2 = (int(tip_x - head_len * Dx - head_len * 0.4 * perp_x),
                 int(tip_y - head_len * Dy - head_len * 0.4 * perp_y))
        draw.polygon([tip, base1, base2], fill=(0, 200, 255, 230))

    return Image.alpha_composite(overlay, arrow_layer)


def _draw_airfree_arrow_mpl(ax, fan):
    """Draw a direction arrow on the matplotlib heatmap for an AirFree fan."""
    cx, cy = fan["x"], fan["y"]
    hw = fan["half_w"]
    hh = fan["half_h"]
    rect_angle = math.radians(fan.get("angle", 0))
    flow_angle_rad = math.radians(fan.get("flow_angle", 0))

    angle_diff = flow_angle_rad - rect_angle
    u_extent = hw * abs(math.cos(angle_diff)) + hh * abs(math.sin(angle_diff))
    Dx = math.cos(flow_angle_rad)
    Dy = math.sin(flow_angle_rad)

    # Arrow from back face to beyond front face
    back_x = cx - u_extent * Dx
    back_y = cy - u_extent * Dy
    tip_x = cx + (u_extent + min(hw, hh) * 0.8) * Dx
    tip_y = cy + (u_extent + min(hw, hh) * 0.8) * Dy

    ax.annotate(
        "", xy=(tip_x, tip_y), xytext=(back_x, back_y),
        arrowprops=dict(arrowstyle="->", color="white", lw=2.5),
    )

    # Label at the front face center
    label_x = cx + u_extent * Dx * 0.5
    label_y = cy + u_extent * Dy * 0.5
    ax.text(label_x, label_y, "AirFree",
            ha="center", va="center", fontsize=7, color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#0055AA", alpha=0.75))


def render():
    user = get_current_user()
    if not user or user["role"] not in ("superadmin", "admin"):
        st.error("Acceso denegado.")
        return

    _init_state()

    st.title("Simulador de Flujo de Aire")

    with st.sidebar:
        st.subheader("Herramientas de Dibujo")
        tool_options = ["transform", "circle", "rect", "polygon_tool", "flow_polygon"]
        tool_labels = {
            "transform": "Seleccionar/Mover",
            "circle": "Abanico Techo (Circulo)",
            "rect": "Abanico Pedestal (AirFree)",
            "polygon_tool": "Obstáculo (Polígono)",
            "flow_polygon": "✏️ Delimitar flujo",
        }
        selected_tool = st.radio(
            "Modo:",
            tool_options,
            format_func=lambda x: tool_labels[x],
        )

        is_polygon_mode = selected_tool == "polygon_tool"
        is_flow_polygon_mode = selected_tool == "flow_polygon"

        if is_polygon_mode or is_flow_polygon_mode:
            drawing_mode = "point"
            stroke_color = "#FF0000" if is_polygon_mode else "#9B59B6"
        else:
            drawing_mode = selected_tool
            stroke_color = (
                "#FF6600" if selected_tool == "circle"
                else "#00AAFF" if selected_tool == "rect"
                else "#FF0000"
            )

        # ── Obstacle polygon controls ──────────────────────────────────────────
        if is_polygon_mode:
            st.divider()
            st.subheader("Dibujo de Obstáculo")
            temp_pts = st.session_state["polygon_points_temp"]
            st.caption(f"Puntos actuales: {len(temp_pts)}")
            if len(temp_pts) >= 3:
                obs_size_temp = st.selectbox(
                    "Tipo de obstáculo",
                    ["Ch", "M", "G", "XL"],
                    index=3,
                    format_func=lambda k: OBS_DISPLAY_NAMES[k],
                    key="new_obs_size",
                )
                if st.button("Finalizar y Guardar Obstáculo", type="primary"):
                    st.session_state["saved_obstacles"].append({
                        "points": list(temp_pts),
                        "size": obs_size_temp,
                        "transmission": SIZE_TRANSMISSION[obs_size_temp],
                    })
                    st.session_state["polygon_points_temp"] = []
                    st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                    st.rerun()
            elif len(temp_pts) > 0:
                st.info("Necesitas al menos 3 puntos para formar un obstaculo.")
            if st.button("Cancelar Poligono"):
                st.session_state["polygon_points_temp"] = []
                st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                st.rerun()

        # ── Flow-limit polygon controls ────────────────────────────────────────
        if is_flow_polygon_mode:
            st.divider()
            st.subheader("✏️ Delimitar zona de flujo")
            st.caption(
                "Haz clic en el canvas para añadir vértices. "
                "Dentro de esta zona el flujo se atenúa hasta cero en el borde."
            )
            fp_pts = st.session_state["flow_polygon_points_temp"]
            st.caption(f"Puntos actuales: {len(fp_pts)}")
            if len(fp_pts) >= 3:
                if st.button("Terminar polígono", type="primary", key="finish_flow_poly_sb"):
                    st.session_state["flow_limits"].append({
                        "id": np.random.randint(0, 10_000_000),
                        "points": list(fp_pts),
                    })
                    st.session_state["flow_polygon_points_temp"] = []
                    st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                    st.rerun()
            elif len(fp_pts) > 0:
                st.info("Necesitas al menos 3 puntos para cerrar la zona.")
            if st.button("Cancelar polígono", key="cancel_flow_poly_sb"):
                st.session_state["flow_polygon_points_temp"] = []
                st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                st.rerun()

        if len(st.session_state["saved_obstacles"]) > 0:
            st.divider()
            st.subheader("Obstáculos Guardados")
            for i, obs in enumerate(st.session_state["saved_obstacles"]):
                # Row 1: name + delete button
                row1_cols = st.columns([5, 1])
                with row1_cols[0]:
                    st.write(f"**{i+1}.** {OBS_DISPLAY_NAMES.get(obs['size'], obs['size'])} ({len(obs['points'])} vértices)")
                with row1_cols[1]:
                    if st.button("✕", key=f"del_obs_{i}"):
                        st.session_state["saved_obstacles"].pop(i)
                        st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                        st.rerun()
                # Row 2: full-width type selector
                new_size = st.selectbox(
                    f"Tipo obstáculo {i+1}",
                    ["Ch", "M", "G", "XL"],
                    index=["Ch", "M", "G", "XL"].index(obs["size"]),
                    format_func=lambda k: OBS_DISPLAY_NAMES[k],
                    key=f"saved_obs_size_{i}",
                    label_visibility="collapsed",
                )
                if new_size != obs["size"]:
                    st.session_state["saved_obstacles"][i]["size"] = new_size
                    st.session_state["saved_obstacles"][i]["transmission"] = SIZE_TRANSMISSION[new_size]

        # ── Saved flow-limit delimiters ────────────────────────────────────────
        if st.session_state["flow_limits"]:
            st.divider()
            st.subheader("🟣 Zonas de flujo delimitadas")
            for i, poly_data in enumerate(st.session_state["flow_limits"]):
                cols = st.columns([5, 1])
                with cols[0]:
                    n_pts = len(poly_data.get("points", []))
                    st.write(f"**Zona {i + 1}** ({n_pts} vértices)")
                with cols[1]:
                    if st.button("✕", key=f"del_flow_{i}"):
                        st.session_state["flow_limits"].pop(i)
                        st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                        st.rerun()

        # AirFree angle controls — shown in sidebar when fans are present on canvas
        # We use a placeholder list stored in session state, updated after canvas parse
        airfree_sidebar_data = st.session_state.get("airfree_sidebar_fans", [])
        if airfree_sidebar_data:
            st.divider()
            st.subheader("Direccion de flujo — AirFree")
            st.caption("0°=derecha  90°=abajo  180°=izquierda  270°=arriba")
            for i, fan in enumerate(airfree_sidebar_data):
                key = f"airfree_angle_{i}"
                default_angle = st.session_state["airfree_angles"].get(str(i), 0)
                angle = st.slider(
                    f"AirFree {i+1} — angulo",
                    min_value=0, max_value=359,
                    value=default_angle,
                    step=5,
                    format="%d°",
                    key=key,
                )
                st.session_state["airfree_angles"][str(i)] = angle

            # Small arrow preview in sidebar
            if "sim_bg_image" in st.session_state:
                _bg = st.session_state["sim_bg_image"]
                fans_with_angles = []
                for i, fan in enumerate(airfree_sidebar_data):
                    f2 = dict(fan)
                    f2["flow_angle"] = st.session_state["airfree_angles"].get(str(i), 0)
                    fans_with_angles.append(f2)
                arrow_preview = _draw_fans_on_bg(_bg, fans_with_angles)
                st.image(arrow_preview, caption="Vista previa dirección", use_container_width=True)

        st.divider()
        st.subheader("Parametros de Simulacion")
        decay_rate = st.slider("Tasa de decaimiento", 0.01, 0.50, 0.10, 0.01,
                               help="Mayor valor = el aire llega menos lejos")
        multiplier = st.slider("Multiplicador de intensidad", 1.0, 20.0, 10.0, 0.5)
        resolution = st.selectbox("Resolucion", ["Baja", "Media", "Alta"], index=1)
        use_los = st.checkbox("Linea de vista (bloqueo por obstaculos)", value=True)
        heatmap_alpha = st.slider(
            "Opacidad del mapa termico",
            min_value=0.3, max_value=1.0, value=0.6, step=0.05,
            help="Ajusta la transparencia del mapa de calor para ver el plano de fondo",
        )

        st.caption("Contexto Ambiental")
        # Selectbox with fixed options 20–45 °C (as defined in the thermal sensation table)
        _temp_options = list(range(20, 46))
        ambient_temp = st.selectbox(
            "🌡️ Temp. Ambiente (°C)",
            options=_temp_options,
            index=_temp_options.index(30),  # default: 30 °C
            help="Temperatura ambiente del espacio (20–45 °C)",
        )
        _now = datetime.now()
        sim_date = st.date_input(
            "📅 Fecha",
            value=_now.date(),
        )
        sim_time = st.time_input(
            "⏰ Hora",
            value=_now.time().replace(second=0, microsecond=0),
        )
        air_speed = st.radio(
            "💨 Velocidad del aire",
            options=["1 m/s", "2 m/s", "3 m/s"],
            index=0,
            horizontal=True,
        )
        # Map label → numeric speed for table lookup
        _speed_map = {"1 m/s": 1.0, "2 m/s": 2.0, "3 m/s": 3.0}
        _speed_numeric = _speed_map[air_speed]
        thermal_change = calcular_sensacion_termica(float(ambient_temp), _speed_numeric)
        st.metric(
            "❄️ Sensación térmica calculada",
            f"{thermal_change} °C",
            help="Calculado automáticamente según Temp. Ambiente y Velocidad del aire (tabla Kale Fans América)",
        )

        st.divider()
        st.subheader("Vista Lateral (Elevación)")
        show_side_view = st.checkbox("Mostrar vista lateral (elevación)", value=False)
        if show_side_view:
            ceiling_height_m = st.slider(
                "📏 Altura del techo (m)", 2.0, 50.0, 3.0, 0.5,
                help="Altura total del espacio desde el suelo al techo (2–50 m)",
            )
            # Pedestal max is capped at ceiling height minus a small margin
            pedestal_max = max(0.5, ceiling_height_m - 0.5)
            pedestal_default = min(1.5, pedestal_max)
            pedestal_height_m = st.slider(
                "Altura ventiladores pedestal (m)", 0.5, pedestal_max, pedestal_default, 0.1,
                help="Altura a la que se ubican los ventiladores de pedestal",
            )
        else:
            ceiling_height_m = 3.0
            pedestal_height_m = 1.5

        show_streamlines = st.checkbox("Mostrar flujo de aire (líneas de corriente)", value=False)
        if show_streamlines:
            streamlines_opacity = st.slider(
                "Opacidad de líneas",
                min_value=0.1, max_value=1.0, value=0.7, step=0.05,
                help="Transparencia de las líneas de corriente superpuestas",
            )
        else:
            streamlines_opacity = 0.7

        st.divider()
        col_limpiar, col_cerrar = st.columns(2)
        with col_limpiar:
            if st.button("Limpiar Todo", use_container_width=True):
                st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                st.session_state["saved_obstacles"] = []
                st.session_state["polygon_points_temp"] = []
                st.session_state["airfree_angles"] = {}
                st.session_state["airfree_sidebar_fans"] = []
                st.session_state["saved_fans_raw"] = []
                st.session_state["_prev_canvas_key"] = None
                # Also clear flow-limit state
                st.session_state["flow_limits"] = []
                st.session_state["flow_polygon_points_temp"] = []
                for k in list(st.session_state.keys()):
                    if k.startswith("saved_obs_size_") or k.startswith("airfree_angle_"):
                        del st.session_state[k]
                for key in ["sim_bg_image", "sim_img_w", "sim_img_h"]:
                    st.session_state.pop(key, None)
                st.rerun()
        with col_cerrar:
            if st.button("Cerrar Sesion", use_container_width=True):
                from utils.auth import logout
                logout()
                st.rerun()

    # --- Plan upload ---
    uploaded_file = st.file_uploader("Sube un plano arquitectonico", type=["png", "jpg", "jpeg"])
    if uploaded_file:
        bg_image = Image.open(uploaded_file).copy()
        orig_w, orig_h = bg_image.size
        max_w = 800
        if orig_w > max_w:
            ratio = max_w / orig_w
            bg_image = bg_image.resize((int(orig_w * ratio), int(orig_h * ratio)))
        bg_image = bg_image.convert("RGBA")
        st.session_state["sim_bg_image"] = bg_image
        st.session_state["sim_img_w"] = bg_image.size[0]
        st.session_state["sim_img_h"] = bg_image.size[1]

    if "sim_bg_image" not in st.session_state:
        st.info("Sube una imagen de plano para comenzar la simulacion.")
        return

    bg_image = st.session_state["sim_bg_image"]
    w = st.session_state["sim_img_w"]
    h = st.session_state["sim_img_h"]

    # --- Canvas ---
    st.subheader("Dibuja ventiladores y obstaculos")

    if is_polygon_mode:
        # ── Obstacle polygon drawing mode ──────────────────────────────────────
        temp_pts = st.session_state["polygon_points_temp"]
        st.caption("Haz clic en el canvas para agregar vertices del obstaculo.")
        preview_img = _draw_polygon_preview(
            bg_image, temp_pts,
            saved_fans_raw=st.session_state.get("saved_fans_raw", []),
            saved_obstacles=st.session_state.get("saved_obstacles", []),
            flow_limits=st.session_state.get("flow_limits", []),
        )
        canvas_result = st_canvas(
            fill_color="rgba(255, 0, 0, 0.3)",
            stroke_width=3,
            stroke_color="#FF0000",
            background_color="#ffffff",
            background_image=preview_img,
            width=w,
            height=h,
            drawing_mode="point",
            point_display_radius=5,
            key=str(st.session_state["sim_canvas_key"]) + "_poly",
            display_toolbar=False,
        )
        if canvas_result.json_data is not None:
            point_objects = canvas_result.json_data.get("objects", [])
            new_points = []
            for obj in point_objects:
                if obj.get("type") == "circle":
                    cx = obj.get("left", 0) + obj.get("radius", 0)
                    cy = obj.get("top", 0) + obj.get("radius", 0)
                    new_points.append([cx, cy])
            if len(new_points) > len(temp_pts):
                st.session_state["polygon_points_temp"] = new_points
                st.rerun()

        # Status panel (mirrors sidebar for visibility)
        n_pts = len(st.session_state["polygon_points_temp"])
        st.info(f"Puntos registrados: **{n_pts}** {'— mínimo 3 para finalizar' if n_pts < 3 else '— listo para finalizar'}")
        if n_pts >= 3:
            obs_size_main = st.selectbox(
                "Tipo de obstáculo",
                ["Ch", "M", "G", "XL"],
                index=3,
                format_func=lambda k: OBS_DISPLAY_NAMES[k],
                key="new_obs_size_main",
            )
            col_fin1, col_fin2 = st.columns(2)
            with col_fin1:
                if st.button("Finalizar y Guardar Obstáculo", type="primary", key="finalizar_main"):
                    st.session_state["saved_obstacles"].append({
                        "points": list(st.session_state["polygon_points_temp"]),
                        "size": obs_size_main,
                        "transmission": SIZE_TRANSMISSION[obs_size_main],
                    })
                    st.session_state["polygon_points_temp"] = []
                    st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                    st.rerun()
            with col_fin2:
                if st.button("Cancelar Polígono", key="cancelar_main"):
                    st.session_state["polygon_points_temp"] = []
                    st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                    st.rerun()
        elif n_pts > 0:
            if st.button("Cancelar Polígono", key="cancelar_main_early"):
                st.session_state["polygon_points_temp"] = []
                st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                st.rerun()

    elif is_flow_polygon_mode:
        # ── Flow-limit polygon drawing mode ────────────────────────────────────
        fp_pts = st.session_state["flow_polygon_points_temp"]
        st.caption("🟣 Haz clic en el canvas para añadir vértices del delimitador de flujo.")
        preview_img = _draw_polygon_preview(
            bg_image, [],
            saved_fans_raw=st.session_state.get("saved_fans_raw", []),
            saved_obstacles=st.session_state.get("saved_obstacles", []),
            flow_limits=st.session_state.get("flow_limits", []),
            temp_flow_points=fp_pts,
            drawing_flow=True,
        )
        canvas_result = st_canvas(
            fill_color="rgba(155, 89, 182, 0.3)",
            stroke_width=3,
            stroke_color="#9B59B6",
            background_color="#ffffff",
            background_image=preview_img,
            width=w,
            height=h,
            drawing_mode="point",
            point_display_radius=5,
            key=str(st.session_state["sim_canvas_key"]) + "_flow_poly",
            display_toolbar=False,
        )
        if canvas_result.json_data is not None:
            point_objects = canvas_result.json_data.get("objects", [])
            new_fp = []
            for obj in point_objects:
                if obj.get("type") == "circle":
                    cx = obj.get("left", 0) + obj.get("radius", 0)
                    cy = obj.get("top", 0) + obj.get("radius", 0)
                    new_fp.append([cx, cy])
            if len(new_fp) > len(fp_pts):
                st.session_state["flow_polygon_points_temp"] = new_fp
                st.rerun()

        # Status + finish panel below canvas
        n_fp = len(st.session_state["flow_polygon_points_temp"])
        st.info(f"🟣 Puntos registrados: **{n_fp}** {'— mínimo 3 para cerrar la zona' if n_fp < 3 else '— listo para terminar'}")
        if n_fp >= 3:
            col_fp1, col_fp2 = st.columns(2)
            with col_fp1:
                if st.button("Terminar polígono", type="primary", key="finish_flow_poly_main"):
                    st.session_state["flow_limits"].append({
                        "id": np.random.randint(0, 10_000_000),
                        "points": list(st.session_state["flow_polygon_points_temp"]),
                    })
                    st.session_state["flow_polygon_points_temp"] = []
                    st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                    st.rerun()
            with col_fp2:
                if st.button("Cancelar", key="cancel_flow_poly_main"):
                    st.session_state["flow_polygon_points_temp"] = []
                    st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                    st.rerun()
        elif n_fp > 0:
            if st.button("Cancelar", key="cancel_flow_poly_main_early"):
                st.session_state["flow_polygon_points_temp"] = []
                st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                st.rerun()

    else:
        st.caption("Circulo = abanico techo  |  Rectangulo = abanico AirFree pedestal")
        current_key = str(st.session_state["sim_canvas_key"])
        canvas_was_reset = st.session_state["_prev_canvas_key"] != current_key
        st.session_state["_prev_canvas_key"] = current_key
        fans_for_init = st.session_state.get("saved_fans_raw", []) if canvas_was_reset else []
        initial = _build_initial_drawing(
            w, h, st.session_state["saved_obstacles"],
            saved_fans_raw=fans_for_init,
        )
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.2)",
            stroke_width=2,
            stroke_color=stroke_color,
            background_color="#ffffff",
            background_image=bg_image,
            width=w,
            height=h,
            drawing_mode=drawing_mode,
            initial_drawing=initial if len(initial["objects"]) > 0 else None,
            key=current_key,
            display_toolbar=True,
        )

    if canvas_result.json_data is None:
        return

    objects = canvas_result.json_data.get("objects", [])

    if not is_polygon_mode and not is_flow_polygon_mode:
        fans_circ, fans_airfree, fans_oval, canvas_obstacles = parse_canvas_objects(objects)
        raw_fans = [
            obj for obj in objects
            if obj.get("type", "") in ("circle", "rect", "ellipse")
        ]
        if raw_fans:
            st.session_state["saved_fans_raw"] = raw_fans
    else:
        fans_circ, fans_airfree, fans_oval, _ = parse_canvas_objects(
            st.session_state.get("saved_fans_raw", [])
        )

    # Update sidebar AirFree fan data for next render cycle
    if fans_airfree:
        st.session_state["airfree_sidebar_fans"] = [dict(f) for f in fans_airfree]
    else:
        st.session_state["airfree_sidebar_fans"] = []

    # Apply stored angles from sidebar sliders
    for i, fan in enumerate(fans_airfree):
        fans_airfree[i]["flow_angle"] = st.session_state["airfree_angles"].get(str(i), 0)

    all_obstacles = list(st.session_state["saved_obstacles"])

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Abanicos Techo", len(fans_circ))
    with col_m2:
        st.metric("Abanicos AirFree", len(fans_airfree))
    with col_m3:
        st.metric("Obstáculos", len(all_obstacles))

    # --- Simulation ---
    sim_btn = st.button("Generar Mapa de Calor", type="primary")
    # Placeholder anchored immediately below the button so results render in-view
    result_placeholder = st.empty()

    if sim_btn:
        total_fans = len(fans_circ) + len(fans_airfree) + len(fans_oval)
        if total_fans == 0:
            st.warning("Dibuja al menos un ventilador antes de simular.")
            return

        sim_obstacles = [
            {
                "points": np.array(obs["points"], dtype=np.int32),
                "size": obs["size"],
                "transmission": obs["transmission"],
            }
            for obs in all_obstacles
        ]

        progress_bar = st.progress(0, text="Calculando flujo de aire...")

        def update_progress(val):
            progress_bar.progress(min(val, 1.0), text=f"Procesando ventilador... {int(val*100)}%")

        total_intensity, sim_w, sim_h, xl_shadow = run_simulation(
            fans_circ, fans_airfree, fans_oval, sim_obstacles,
            w, h, decay_rate, multiplier, resolution, use_los,
            progress_callback=update_progress,
        )
        progress_bar.empty()

        fig, ax = plt.subplots(figsize=(10, h / w * 10))
        ax.imshow(bg_image)

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
            extent=[0, w, h, 0], vmin=0, vmax=100,
        )

        # XL shadow overlay (red)
        if np.any(xl_shadow):
            shadow_rgba = np.zeros((sim_h, sim_w, 4), dtype=np.float32)
            shadow_rgba[xl_shadow, 0] = 1.0
            shadow_rgba[xl_shadow, 3] = 0.5
            ax.imshow(shadow_rgba, extent=[0, w, h, 0], interpolation="bilinear")

        # Direction arrows for each AirFree fan
        for fan in fans_airfree:
            _draw_airfree_arrow_mpl(ax, fan)

        # Obstacle outlines
        for obs in all_obstacles:
            pts = obs["points"]
            if len(pts) >= 3:
                poly_x = [p[0] for p in pts] + [pts[0][0]]
                poly_y = [p[1] for p in pts] + [pts[0][1]]
                size_label = obs.get("size", "XL")
                color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
                ax.plot(poly_x, poly_y, color=color_map.get(size_label, "#FF0000"),
                        linewidth=2, linestyle="--")
                cx_o = sum(p[0] for p in pts) / len(pts)
                cy_o = sum(p[1] for p in pts) / len(pts)
                map_label = OBS_MAP_LABELS.get(size_label, size_label)
                ax.text(cx_o, cy_o, map_label, ha="center", va="center",
                        fontsize=8, fontweight="bold", color="white",
                        bbox=dict(boxstyle="round,pad=0.2",
                                  facecolor=color_map.get(size_label, "red"), alpha=0.7))

        # Small cartesian axis compass in the upper-left corner
        pad = max(w, h) * 0.035
        arrow_len = max(w, h) * 0.045
        ox, oy = pad, pad
        ax.annotate("", xy=(ox + arrow_len, oy), xytext=(ox, oy),
                    arrowprops=dict(arrowstyle="->", color="white", lw=1.5))
        ax.annotate("", xy=(ox, oy + arrow_len), xytext=(ox, oy),
                    arrowprops=dict(arrowstyle="->", color="white", lw=1.5))
        ax.text(ox + arrow_len + 3, oy, "X", color="white", fontsize=7, va="center", fontweight="bold")
        ax.text(ox, oy + arrow_len + 3, "Y", color="white", fontsize=7, ha="center", fontweight="bold")

        # Contextual annotations: ambient temp, date/time, thermal sensation
        fecha_str = sim_date.strftime("%Y-%m-%d")
        hora_str = sim_time.strftime("%H:%M")
        annotation_text = (
            f"Temp. Ambiente: {ambient_temp} °C    "
            f"Fecha: {fecha_str} | Hora: {hora_str}    "
            f"Sensación térmica: {thermal_change} °C a {air_speed}"
        )
        fig.text(
            0.5, 0.01, annotation_text,
            ha="center", va="bottom", fontsize=7, color="white",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#1a1a2e", alpha=0.75),
        )

        ax.axis("off")

        # Dynamic colorbar: map 0-100 internal scale to real temperatures
        # 0 (red) = Temp. Ambiente, 100 (blue) = Sensación térmica calculada
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        if thermal_change < ambient_temp:
            # Normal case: cooling occurs, blue = cooler, red = warmer
            cbar_ticks = [0, 25, 50, 75, 100]
            cbar_labels = [
                f"{ambient_temp - t / 100.0 * (ambient_temp - thermal_change):.1f} °C"
                for t in cbar_ticks
            ]
            cbar.set_ticks(cbar_ticks)
            cbar.set_ticklabels(cbar_labels)
            cbar.set_label(
                f"Temperatura  ▼ {ambient_temp}°C (ambiente) → {thermal_change}°C (sens. térmica) ▲",
                fontsize=7,
            )
        else:
            # Edge case: sensation >= ambient temp — show warning, keep raw scale
            cbar.set_label("Sensación térmica ≥ Temp. Ambiente — sin diferencia de enfriamiento", fontsize=7, color="orange")
        cbar.ax.tick_params(labelsize=7)

        # --- Streamlines ---
        fig_stream = None
        if show_streamlines:
            stream_lines, fan_origins, stream_w, stream_h, stream_obs_mask, stream_scaled_obs = compute_streamlines(
                fans_circ, fans_airfree, fans_oval, sim_obstacles,
                w, h, decay_rate, multiplier, resolution, use_los,
            )
            fig_stream = render_streamlines_figure(
                bg_image, stream_lines, fan_origins, stream_w, stream_h,
                w, h, all_obstacles, stream_scaled_obs,
            )

        # --- Side view ---
        fig_side = None
        if show_side_view:
            side_intensity, side_w, side_h = run_side_view_simulation(
                fans_circ, fans_airfree, fans_oval,
                w, ceiling_height_m, pedestal_height_m,
                decay_rate, multiplier, resolution,
            )
            fig_side = render_side_view_figure(
                side_intensity, side_w, side_h,
                fans_circ, fans_airfree, fans_oval,
                w, ceiling_height_m, pedestal_height_m,
                heatmap_alpha,
                ambient_temp=ambient_temp,
                sim_date=sim_date,
                sim_time=sim_time,
                thermal_change=thermal_change,
                air_speed=air_speed,
            )

        # Render results inside the anchored placeholder so they appear immediately
        with result_placeholder.container():
            st.subheader("Vista Superior — Mapa de Calor")
            st.pyplot(fig)

            if fig_stream is not None:
                st.divider()
                st.subheader("Flujo de Aire — Líneas de Corriente")
                st.pyplot(fig_stream)

            if fig_side is not None:
                st.divider()
                st.subheader("Vista Lateral (Elevación)")
                st.pyplot(fig_side)

            # --- Export ---
            st.divider()
            st.subheader("Exportar Resultados")

            buf_img = io.BytesIO()
            fig.savefig(buf_img, format="png", bbox_inches="tight", pad_inches=0, dpi=150)
            buf_img.seek(0)

            intensity_clean = np.nan_to_num(total_intensity, nan=0.0)
            ys, xs = np.mgrid[0:sim_h, 0:sim_w]
            x_coords = (xs * (w / sim_w)).flatten()
            y_coords = (ys * (h / sim_h)).flatten()
            intensities = intensity_clean.flatten()
            # Map intensity to real temperature:
            # intensity_norm = 0 → Temp. Ambiente (red), intensity_norm = 1 → Sensación térmica (blue)
            _csv_raw_max = float(np.max(intensity_clean)) if np.any(intensity_clean > 0) else 1.0
            _csv_raw_max = max(_csv_raw_max, 0.01)
            intensity_norm = intensities / _csv_raw_max
            temp_delta = float(ambient_temp) - float(thermal_change)
            temp_real = float(ambient_temp) - intensity_norm * temp_delta
            df = pd.DataFrame({
                "x": np.round(x_coords, 1),
                "y": np.round(y_coords, 1),
                "intensidad": np.round(intensities, 4),
                "temperatura_real_C": np.round(temp_real, 2),
            })
            csv_data = df.to_csv(index=False)

            export_options = ["Vista Superior"]
            if fig_stream is not None:
                export_options.append("Flujo de Aire")
            if fig_side is not None:
                export_options.append("Vista Lateral")

            if len(export_options) > 1:
                export_view = st.radio(
                    "Exportar vista:",
                    export_options,
                    horizontal=True,
                    key="export_view_select",
                )
            else:
                export_view = "Vista Superior"

            if export_view == "Vista Superior":
                st.download_button("Descargar Imagen (PNG)", buf_img.getvalue(), "mapa_calor.png", "image/png")
            elif export_view == "Flujo de Aire":
                buf_stream = io.BytesIO()
                fig_stream.savefig(buf_stream, format="png", bbox_inches="tight", pad_inches=0, dpi=150)
                buf_stream.seek(0)
                st.download_button("Descargar Flujo de Aire (PNG)", buf_stream.getvalue(), "flujo_aire.png", "image/png")
            elif export_view == "Vista Lateral":
                buf_side = io.BytesIO()
                fig_side.savefig(buf_side, format="png", bbox_inches="tight", pad_inches=0, dpi=150)
                buf_side.seek(0)
                st.download_button("Descargar Vista Lateral (PNG)", buf_side.getvalue(), "vista_lateral.png", "image/png")

            # --- Save project ---
            st.divider()
            st.subheader("Guardar como Proyecto")
            st.caption("La asignacion a cliente se gestiona desde la vista Proyectos.")
            nombre_proy = st.text_input(
                "Nombre del proyecto",
                value=f"Simulacion_{datetime.now().strftime('%Y%m%d_%H%M')}",
            )

            if st.button("Guardar Proyecto"):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.makedirs("outputs", exist_ok=True)

                img_path = f"outputs/{timestamp}_resultado.png"
                csv_path = f"outputs/{timestamp}_datos.csv"
                orig_path = f"outputs/{timestamp}_original.png"

                with open(img_path, "wb") as f:
                    f.write(buf_img.getvalue())
                with open(csv_path, "w") as f:
                    f.write(csv_data)
                bg_image.save(orig_path)

                proyecto_id = create_proyecto(
                    nombre=nombre_proy,
                    admin_id=user["id"],
                    imagen_original=orig_path,
                    imagen_resultado=img_path,
                    datos_csv=csv_path,
                    asignado_a=None,
                )
                st.success(f"Proyecto '{nombre_proy}' guardado exitosamente (ID: {proyecto_id}).")

        plt.close(fig)
        if fig_stream is not None:
            plt.close(fig_stream)
        if fig_side is not None:
            plt.close(fig_side)
