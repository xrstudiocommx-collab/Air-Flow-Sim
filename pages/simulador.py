import streamlit as st
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from matplotlib.colors import LinearSegmentedColormap
import io
import os
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


def render():
    user = get_current_user()
    if not user or user["role"] not in ("superadmin", "admin"):
        st.error("Acceso denegado.")
        return

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
        drawing_mode = st.radio(
            "Modo:",
            ("transform", "circle", "rect", "polygon"),
            format_func=lambda x: {
                "transform": "Seleccionar/Mover",
                "circle": "Abanico Techo (Circulo)",
                "rect": "Abanico Pedestal (Rectangulo/Ovalo)",
                "polygon": "Obstaculo (Poligono)",
            }[x],
        )

        stroke_color = "#FF6600" if drawing_mode == "circle" else (
            "#00AAFF" if drawing_mode == "rect" else "#FF0000"
        )

        st.divider()
        if st.button("Limpiar Canvas"):
            st.session_state["sim_canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
            for k in list(st.session_state.keys()):
                if k.startswith("obstacle_sizes"):
                    del st.session_state[k]
            if "sim_bg_image" in st.session_state:
                del st.session_state["sim_bg_image"]
            if "sim_img_w" in st.session_state:
                del st.session_state["sim_img_w"]
            if "sim_img_h" in st.session_state:
                del st.session_state["sim_img_h"]
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
    st.caption("Circulo = abanico techo | Rectangulo = abanico pedestal (AirFree) | Poligono = obstaculo")

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.2)",
        stroke_width=2,
        stroke_color=stroke_color,
        background_color="#ffffff",
        background_image=bg_image,
        width=w,
        height=h,
        drawing_mode=drawing_mode,
        key=str(st.session_state.get("sim_canvas_key", "sim_canvas")),
        display_toolbar=True,
    )

    if canvas_result.json_data is None:
        return

    objects = canvas_result.json_data.get("objects", [])
    fans_circ, fans_oval, obstacles = parse_canvas_objects(objects)

    if "obstacle_sizes" not in st.session_state:
        st.session_state["obstacle_sizes"] = {}

    if len(obstacles) > 0:
        st.subheader("Configurar obstaculos")
        for i, obs in enumerate(obstacles):
            key = f"obs_size_{i}"
            cols = st.columns([3, 1])
            with cols[0]:
                st.write(f"Obstaculo {i + 1}")
            with cols[1]:
                prev_size = st.session_state.get(f"obstacle_sizes_{i}", "XL")
                size = st.selectbox(
                    f"Tamano {i+1}",
                    ["Ch", "M", "G", "XL"],
                    index=["Ch", "M", "G", "XL"].index(prev_size),
                    key=key,
                    label_visibility="collapsed",
                )
                st.session_state[f"obstacle_sizes_{i}"] = size
                obs["size"] = size
                obs["transmission"] = SIZE_TRANSMISSION[size]

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Abanicos Techo", len(fans_circ))
    with col_m2:
        st.metric("Abanicos Pedestal", len(fans_oval))
    with col_m3:
        st.metric("Obstaculos", len(obstacles))

    if st.button("Generar Mapa de Calor", type="primary"):
        total_fans = len(fans_circ) + len(fans_oval)
        if total_fans == 0:
            st.warning("Dibuja al menos un ventilador antes de simular.")
            return

        progress_bar = st.progress(0, text="Calculando flujo de aire...")

        def update_progress(val):
            progress_bar.progress(min(val, 1.0), text=f"Procesando ventilador... {int(val * 100)}%")

        total_intensity, sim_w, sim_h = run_simulation(
            fans_circ, fans_oval, obstacles,
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
