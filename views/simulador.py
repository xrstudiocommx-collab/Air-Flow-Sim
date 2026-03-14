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

# Thermographic inverse palette:
#   low intensity  (ambient / warm) → red shades
#   high intensity (core cold flow) → navy blue
CMAP_COLD_AIR = LinearSegmentedColormap.from_list(
    "cold_air_thermo",
    [
        "#FF6347",  # soft red    – ambient temperature (lowest intensity)
        "#FFA500",  # orange      – slightly cooler
        "#FFFF00",  # yellow      – transitioning
        "#FFFFFF",  # white       – mixing zone
        "#4169E1",  # royal blue  – cool air
        "#000080",  # navy        – core cold flow (highest intensity)
    ],
    N=256,
)

from utils.canvas_utils import parse_canvas_objects, SIZE_TRANSMISSION
from utils.simulation import run_simulation
from utils.db import create_proyecto, get_users_by_role
from utils.auth import get_current_user


def _init_state():
    if "sim_canvas_key" not in st.session_state:
        st.session_state["sim_canvas_key"] = "sim_canvas"
    if "saved_obstacles" not in st.session_state:
        st.session_state["saved_obstacles"] = []
    if "polygon_points_temp" not in st.session_state:
        st.session_state["polygon_points_temp"] = []
    if "airfree_angles" not in st.session_state:
        # dict: str(fan_index) -> flow angle in degrees
        st.session_state["airfree_angles"] = {}


def _build_initial_drawing(w, h, saved_obstacles):
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
    return {"version": "4.4.0", "objects": objects}


def _draw_polygon_preview(bg_image, temp_points):
    overlay = bg_image.copy()
    draw = ImageDraw.Draw(overlay)
    r = 4
    for px, py in temp_points:
        draw.ellipse([px - r, py - r, px + r, py + r], fill="red", outline="white")
    if len(temp_points) >= 2:
        flat = [(int(p[0]), int(p[1])) for p in temp_points]
        draw.line(flat, fill="red", width=2)
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

        st.divider()
        st.subheader("Herramientas de Dibujo")
        tool_options = ["transform", "circle", "rect", "polygon_tool"]
        tool_labels = {
            "transform": "Seleccionar/Mover",
            "circle": "Abanico Techo (Circulo)",
            "rect": "Abanico Pedestal (AirFree)",
            "polygon_tool": "Obstaculo (Poligono)",
        }
        selected_tool = st.radio(
            "Modo:",
            tool_options,
            format_func=lambda x: tool_labels[x],
        )

        is_polygon_mode = selected_tool == "polygon_tool"

        if is_polygon_mode:
            drawing_mode = "point"
            stroke_color = "#FF0000"
        else:
            drawing_mode = selected_tool
            stroke_color = (
                "#FF6600" if selected_tool == "circle"
                else "#00AAFF" if selected_tool == "rect"
                else "#FF0000"
            )

        if is_polygon_mode:
            st.divider()
            st.subheader("Dibujo de Obstaculo")
            temp_pts = st.session_state["polygon_points_temp"]
            st.caption(f"Puntos actuales: {len(temp_pts)}")
            if len(temp_pts) >= 3:
                obs_size_temp = st.selectbox(
                    "Tamano del obstaculo",
                    ["Ch", "M", "G", "XL"],
                    index=3,
                    key="new_obs_size",
                )
                if st.button("Finalizar y Guardar Obstaculo", type="primary"):
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

        if len(st.session_state["saved_obstacles"]) > 0:
            st.divider()
            st.subheader("Obstaculos Guardados")
            for i, obs in enumerate(st.session_state["saved_obstacles"]):
                cols = st.columns([2, 1, 1])
                with cols[0]:
                    st.write(f"Obstaculo {i+1} ({len(obs['points'])} vertices)")
                with cols[1]:
                    new_size = st.selectbox(
                        f"Tam {i+1}",
                        ["Ch", "M", "G", "XL"],
                        index=["Ch", "M", "G", "XL"].index(obs["size"]),
                        key=f"saved_obs_size_{i}",
                        label_visibility="collapsed",
                    )
                    if new_size != obs["size"]:
                        st.session_state["saved_obstacles"][i]["size"] = new_size
                        st.session_state["saved_obstacles"][i]["transmission"] = SIZE_TRANSMISSION[new_size]
                with cols[2]:
                    if st.button("X", key=f"del_obs_{i}"):
                        st.session_state["saved_obstacles"].pop(i)
                        st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
                        st.rerun()

        st.divider()
        if st.button("Limpiar Todo"):
            st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
            st.session_state["saved_obstacles"] = []
            st.session_state["polygon_points_temp"] = []
            st.session_state["airfree_angles"] = {}
            for k in list(st.session_state.keys()):
                if k.startswith("saved_obs_size_") or k.startswith("airfree_angle_"):
                    del st.session_state[k]
            for key in ["sim_bg_image", "sim_img_w", "sim_img_h"]:
                st.session_state.pop(key, None)
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
        temp_pts = st.session_state["polygon_points_temp"]
        st.caption("Haz clic en el canvas para agregar vertices del obstaculo. Usa 'Finalizar y Guardar' en el sidebar cuando tengas al menos 3 puntos.")
        preview_img = _draw_polygon_preview(bg_image, temp_pts)
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
    else:
        st.caption("Circulo = abanico techo  |  Rectangulo = abanico AirFree pedestal")
        initial = _build_initial_drawing(w, h, st.session_state["saved_obstacles"])
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
            key=str(st.session_state["sim_canvas_key"]),
            display_toolbar=True,
        )

    if canvas_result.json_data is None:
        return

    objects = canvas_result.json_data.get("objects", [])
    fans_circ, fans_airfree, fans_oval, canvas_obstacles = parse_canvas_objects(objects)

    # --- AirFree direction angle controls ---
    if len(fans_airfree) > 0:
        st.subheader("Direccion de flujo — Abanicos AirFree")
        st.caption(
            "Ajusta el angulo de salida del aire para cada abanico pedestal. "
            "0° = derecha, 90° = abajo, 180° = izquierda, 270° = arriba."
        )
        for i, fan in enumerate(fans_airfree):
            key = f"airfree_angle_{i}"
            # Default: 0° (flow pointing right). Preserved across reruns.
            default_angle = st.session_state["airfree_angles"].get(str(i), 0)
            angle = st.slider(
                f"AirFree {i+1}  —  angulo de flujo",
                min_value=0, max_value=359,
                value=default_angle,
                step=5,
                format="%d°",
                key=key,
            )
            st.session_state["airfree_angles"][str(i)] = angle
            fans_airfree[i]["flow_angle"] = angle

        # Draw arrow preview on canvas background so user sees the flow direction
        arrow_bg = _draw_fans_on_bg(bg_image, fans_airfree)
        st.image(arrow_bg, caption="Vista previa de la direccion de flujo (flecha blanca = direccion del aire)", use_container_width=False)

    all_obstacles = list(st.session_state["saved_obstacles"])

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Abanicos Techo", len(fans_circ))
    with col_m2:
        st.metric("Abanicos AirFree", len(fans_airfree))
    with col_m3:
        st.metric("Obstaculos", len(all_obstacles))

    # --- Simulation ---
    if st.button("Generar Mapa de Calor", type="primary"):
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
        display_intensity[display_intensity == 0] = np.nan
        masked = np.ma.masked_invalid(display_intensity)
        valid_vals = total_intensity[total_intensity > 0]
        vmax = float(np.max(valid_vals)) if len(valid_vals) > 0 else 1.0
        vmax = max(vmax, 0.01)
        im = ax.imshow(
            masked, cmap=CMAP_COLD_AIR, alpha=heatmap_alpha,
            extent=[0, w, h, 0], vmin=0, vmax=vmax,
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
                ax.text(cx_o, cy_o, size_label, ha="center", va="center",
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

        ax.axis("off")
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label("Intensidad termica  (azul marino = maximo frio  |  rojo = temperatura ambiente)", fontsize=8)
        st.pyplot(fig)

        # --- Export ---
        st.subheader("Exportar Resultados")
        col_e1, col_e2 = st.columns(2)

        buf_img = io.BytesIO()
        fig.savefig(buf_img, format="png", bbox_inches="tight", pad_inches=0, dpi=150)
        buf_img.seek(0)

        intensity_clean = np.nan_to_num(total_intensity, nan=0.0)
        ys, xs = np.mgrid[0:sim_h, 0:sim_w]
        x_coords = (xs * (w / sim_w)).flatten()
        y_coords = (ys * (h / sim_h)).flatten()
        intensities = intensity_clean.flatten()
        df = pd.DataFrame({
            "x": np.round(x_coords, 1),
            "y": np.round(y_coords, 1),
            "intensidad": np.round(intensities, 4),
        })
        csv_data = df.to_csv(index=False)

        with col_e1:
            st.download_button("Descargar Imagen (PNG)", buf_img.getvalue(), "mapa_calor.png", "image/png")
        with col_e2:
            st.download_button("Descargar Datos (CSV)", csv_data, "datos_flujo.csv", "text/csv")

        # --- Save project ---
        st.divider()
        st.subheader("Guardar como Proyecto")
        nombre_proy = st.text_input(
            "Nombre del proyecto",
            value=f"Simulacion_{datetime.now().strftime('%Y%m%d_%H%M')}",
        )
        clientes = get_users_by_role("cliente")
        asignar_options = [{"id": None, "username": "-- Sin asignar --"}] + clientes
        asignar_sel = st.selectbox(
            "Asignar a cliente (opcional)",
            range(len(asignar_options)),
            format_func=lambda i: asignar_options[i]["username"],
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

            asignado = asignar_options[asignar_sel]["id"]
            proyecto_id = create_proyecto(
                nombre=nombre_proy,
                admin_id=user["id"],
                imagen_original=orig_path,
                imagen_resultado=img_path,
                datos_csv=csv_path,
                asignado_a=asignado,
            )
            st.success(f"Proyecto '{nombre_proy}' guardado exitosamente (ID: {proyecto_id}).")

        plt.close(fig)
