import streamlit as st
import numpy as np
import math
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches
import io
import os
import json
import pandas as pd
from datetime import datetime
from streamlit_drawable_canvas import st_canvas

CMAP_COLD_AIR = LinearSegmentedColormap.from_list(
    "cold_air",
    ["#D32F2F", "#FF8A65", "#FFD54F", "#FFF9C4", "#E0F7FA", "#80DEEA", "#4FC3F7", "#1E88E5", "#0D47A1", "#080A2E"],
    N=256,
)

from utils.canvas_utils import parse_canvas_objects, SIZE_TRANSMISSION
from utils.simulation import run_simulation
from utils.db import create_proyecto, update_proyecto, get_users_by_role
from utils.auth import get_current_user


def _init_state():
    if "sim_canvas_key" not in st.session_state:
        st.session_state["sim_canvas_key"] = "sim_canvas"
    if "saved_obstacles" not in st.session_state:
        st.session_state["saved_obstacles"] = []
    if "polygon_points_temp" not in st.session_state:
        st.session_state["polygon_points_temp"] = []
    if "airfree_front_faces" not in st.session_state:
        # dict: fan_index -> "right" | "left"
        st.session_state["airfree_front_faces"] = {}


def _build_initial_drawing(w, h, saved_obstacles):
    objects = []
    for obs in saved_obstacles:
        pts = obs["points"]
        if len(pts) < 3:
            continue
        fabric_pts = []
        min_x = min(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        for p in pts:
            fabric_pts.append({"x": p[0] - min_x, "y": p[1] - min_y})
        size_label = obs.get("size", "XL")
        color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
        stroke = color_map.get(size_label, "#FF0000")
        objects.append({
            "type": "polygon",
            "left": min_x,
            "top": min_y,
            "fill": "rgba(255,0,0,0.15)",
            "stroke": stroke,
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


def _draw_airfree_arrow(ax, fan):
    """Draw a direction arrow on the heatmap showing front→back flow."""
    cx, cy = fan["x"], fan["y"]
    hw = fan["half_w"]
    hh = fan["half_h"]
    angle_rad = math.radians(fan.get("angle", 0))
    front_face = fan.get("front_face", "right")

    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Arrow goes from front face center to back face center
    if front_face == "right":
        x_front_local, x_back_local = hw, -hw
    else:
        x_front_local, x_back_local = -hw, hw

    def local_to_world(xloc, yloc):
        wx = cx + xloc * cos_a - yloc * sin_a
        wy = cy + xloc * sin_a + yloc * cos_a
        return wx, wy

    fx, fy = local_to_world(x_front_local, 0)
    bx, by = local_to_world(x_back_local, 0)

    ax.annotate(
        "", xy=(bx, by), xytext=(fx, fy),
        arrowprops=dict(arrowstyle="->", color="white", lw=2),
    )
    ax.text((fx + bx) / 2, (fy + by) / 2, "AirFree",
            ha="center", va="center", fontsize=7, color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#00AAFF", alpha=0.7))


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
            stroke_color = "#FF6600" if selected_tool == "circle" else (
                "#00AAFF" if selected_tool == "rect" else "#FF0000"
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
                    st.write(f"Obstaculo {i + 1} ({len(obs['points'])} vertices)")
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
            st.session_state["airfree_front_faces"] = {}
            for k in list(st.session_state.keys()):
                if k.startswith("obstacle_sizes") or k.startswith("saved_obs_size_"):
                    del st.session_state[k]
            for key in ["sim_bg_image", "sim_img_w", "sim_img_h"]:
                st.session_state.pop(key, None)
            st.rerun()

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
        st.caption("Circulo = abanico techo | Rectangulo = abanico AirFree")
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

    # --- Front face selector for each AirFree fan ---
    if len(fans_airfree) > 0:
        st.subheader("Direccion de los Abanicos AirFree")
        st.caption("Selecciona la cara FRONTAL (de donde entra el aire). El flujo sale por la cara opuesta (trasera).")
        for i, fan in enumerate(fans_airfree):
            col_label, col_left, col_right = st.columns([3, 1, 1])
            with col_label:
                st.write(f"AirFree {i + 1}")
            current = st.session_state["airfree_front_faces"].get(str(i), "right")
            with col_left:
                if st.button("← Frontal Izq", key=f"af_left_{i}",
                             type="primary" if current == "left" else "secondary"):
                    st.session_state["airfree_front_faces"][str(i)] = "left"
                    st.rerun()
            with col_right:
                if st.button("Frontal Der →", key=f"af_right_{i}",
                             type="primary" if current == "right" else "secondary"):
                    st.session_state["airfree_front_faces"][str(i)] = "right"
                    st.rerun()
            fans_airfree[i]["front_face"] = st.session_state["airfree_front_faces"].get(str(i), "right")

    all_obstacles = list(st.session_state["saved_obstacles"])

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Abanicos Techo", len(fans_circ))
    with col_m2:
        st.metric("Abanicos AirFree", len(fans_airfree))
    with col_m3:
        st.metric("Obstaculos", len(all_obstacles))

    if st.button("Generar Mapa de Calor", type="primary"):
        total_fans = len(fans_circ) + len(fans_airfree) + len(fans_oval)
        if total_fans == 0:
            st.warning("Dibuja al menos un ventilador antes de simular.")
            return

        sim_obstacles = []
        for obs in all_obstacles:
            sim_obstacles.append({
                "points": np.array(obs["points"], dtype=np.int32),
                "size": obs["size"],
                "transmission": obs["transmission"],
            })

        progress_bar = st.progress(0, text="Calculando flujo de aire...")

        def update_progress(val):
            progress_bar.progress(min(val, 1.0), text=f"Procesando ventilador... {int(val * 100)}%")

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
            masked, cmap=CMAP_COLD_AIR, alpha=0.55,
            extent=[0, w, h, 0], vmin=0, vmax=vmax,
        )

        if np.any(xl_shadow):
            shadow_rgba = np.zeros((sim_h, sim_w, 4), dtype=np.float32)
            shadow_rgba[xl_shadow, 0] = 1.0
            shadow_rgba[xl_shadow, 3] = 0.5
            ax.imshow(shadow_rgba, extent=[0, w, h, 0], interpolation="bilinear")

        # Draw direction arrows for AirFree fans
        for fan in fans_airfree:
            _draw_airfree_arrow(ax, fan)

        # Draw obstacle outlines
        for obs in all_obstacles:
            pts = obs["points"]
            if len(pts) >= 3:
                poly_x = [p[0] for p in pts] + [pts[0][0]]
                poly_y = [p[1] for p in pts] + [pts[0][1]]
                size_label = obs.get("size", "XL")
                color_map = {"Ch": "#00CC00", "M": "#FFAA00", "G": "#FF6600", "XL": "#FF0000"}
                ax.plot(poly_x, poly_y, color=color_map.get(size_label, "#FF0000"),
                        linewidth=2, linestyle="--")
                cx_obs = sum(p[0] for p in pts) / len(pts)
                cy_obs = sum(p[1] for p in pts) / len(pts)
                ax.text(cx_obs, cy_obs, size_label, ha="center", va="center",
                        fontsize=8, fontweight="bold", color="white",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor=color_map.get(size_label, "red"), alpha=0.7))

        ax.axis("off")
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label("Intensidad de flujo (azul = mayor, rojo = menor)", fontsize=9)
        st.pyplot(fig)

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

        st.divider()
        st.subheader("Guardar como Proyecto")
        nombre_proy = st.text_input("Nombre del proyecto", value=f"Simulacion_{datetime.now().strftime('%Y%m%d_%H%M')}")

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

            with open(img_path, "wb") as f:
                f.write(buf_img.getvalue())
            with open(csv_path, "w") as f:
                f.write(csv_data)

            orig_path = f"outputs/{timestamp}_original.png"
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
