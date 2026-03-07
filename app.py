import streamlit as st
import numpy as np
import pandas as pd
from PIL import Image
import matplotlib.pyplot as plt
import io
import cv2
from streamlit_drawable_canvas import st_canvas

st.set_page_config(layout="wide", page_title="Simulador de Flujo de Aire")


def parse_path_to_points(path_data, left, top):
    pts = []
    for cmd in path_data:
        if len(cmd) >= 3 and cmd[0] in ("M", "L"):
            pts.append([cmd[1] + left, cmd[2] + top])
        elif len(cmd) >= 3 and cmd[0] == "Q":
            if len(cmd) >= 5:
                pts.append([cmd[3] + left, cmd[4] + top])
            else:
                pts.append([cmd[1] + left, cmd[2] + top])
    return pts


def compute_visibility_mask(fan_x, fan_y, sim_h, sim_w, obstacle_mask, step_size=1.0):
    visibility = np.ones((sim_h, sim_w), dtype=np.float32)

    yy, xx = np.mgrid[0:sim_h, 0:sim_w]
    dx = xx - fan_x
    dy = yy - fan_y
    dist = np.sqrt(dx**2 + dy**2)
    dist[dist == 0] = 1

    max_dist = np.max(dist)
    num_steps = int(max_dist / step_size) + 1

    for s in range(1, num_steps + 1):
        t = s * step_size / dist
        t = np.clip(t, 0, 1)
        sample_x = (fan_x + t * dx).astype(np.int32)
        sample_y = (fan_y + t * dy).astype(np.int32)

        sample_x = np.clip(sample_x, 0, sim_w - 1)
        sample_y = np.clip(sample_y, 0, sim_h - 1)

        hit = obstacle_mask[sample_y, sample_x] == 0
        visibility[hit] = 0

    return visibility


def compute_visibility_sampled(fan_x, fan_y, sim_h, sim_w, obstacle_mask, num_samples=64):
    visibility = np.ones((sim_h, sim_w), dtype=np.float32)

    yy, xx = np.mgrid[0:sim_h, 0:sim_w]
    dx = xx - fan_x
    dy = yy - fan_y

    for i in range(1, num_samples + 1):
        t = i / num_samples
        sample_x = (fan_x + t * dx).astype(np.int32)
        sample_y = (fan_y + t * dy).astype(np.int32)
        sample_x = np.clip(sample_x, 0, sim_w - 1)
        sample_y = np.clip(sample_y, 0, sim_h - 1)

        hit = obstacle_mask[sample_y, sample_x] == 0
        visibility[hit] = 0

    return visibility


def main():
    st.title("Simulador de Flujo de Aire con Obstaculos")
    st.markdown("""
    Dibuja **Circulos** para representar abanicos y **Poligonos** para representar obstaculos (paredes).
    El flujo de aire se calcula considerando el bloqueo fisico de los obstaculos.
    """)

    with st.sidebar:
        st.header("Configuracion")

        uploaded_file = st.file_uploader("1. Sube un plano (Imagen)", type=['png', 'jpg', 'jpeg'])

        st.divider()
        st.subheader("Herramientas de Dibujo")
        drawing_mode = st.radio(
            "Selecciona modo:",
            ("transform", "circle", "polygon"),
            format_func=lambda x: "Seleccionar/Mover" if x == "transform" else ("Abanico (Circulo)" if x == "circle" else "Obstaculo (Poligono)")
        )

        st.divider()
        st.subheader("Parametros de Simulacion")
        global_decay = st.slider("Tasa de decaimiento global", 0.01, 0.50, 0.08, help="Mayor valor = el aire llega menos lejos")
        intensity_mult = st.slider("Multiplicador de Intensidad", 1.0, 50.0, 10.0)
        resolution = st.select_slider("Resolucion de Simulacion", options=[1, 2, 4, 8, 16], value=8, help="Menor valor = mas calidad pero mas lento")
        use_los = st.checkbox("Bloqueo linea de vista (mas preciso, mas lento)", value=True)

        if st.button("Limpiar Todo"):
            st.session_state["canvas_key"] = f"canvas_{np.random.randint(0, 1000000)}"
            st.rerun()

    if uploaded_file:
        bg_image = Image.open(uploaded_file)
        w, h = bg_image.size
        max_width = 800
        if w > max_width:
            ratio = max_width / w
            bg_image = bg_image.resize((int(w * ratio), int(h * ratio)))
            w, h = bg_image.size

        st.subheader("Dibuja Abanicos y Obstaculos")
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=2,
            stroke_color="#000000",
            background_image=bg_image,
            width=w,
            height=h,
            drawing_mode=drawing_mode,
            key=str(st.session_state.get("canvas_key", "canvas")),
            display_toolbar=True,
        )

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data.get("objects", [])
            fans = []
            obstacles = []

            for obj in objects:
                obj_type = obj.get("type", "")
                left = obj.get("left", 0)
                top = obj.get("top", 0)
                scale_x = obj.get("scaleX", 1)
                scale_y = obj.get("scaleY", 1)

                if obj_type == "circle":
                    radius = obj.get("radius", 0)
                    fans.append({
                        "x": left + radius * scale_x,
                        "y": top + radius * scale_y,
                        "r": radius * scale_x
                    })
                elif obj_type == "polygon":
                    if "points" in obj:
                        pts = []
                        for p in obj["points"]:
                            pts.append([p["x"] * scale_x + left, p["y"] * scale_y + top])
                        if len(pts) >= 3:
                            obstacles.append(np.array(pts, dtype=np.int32))
                elif obj_type == "path":
                    if "path" in obj:
                        pts = parse_path_to_points(obj["path"], left, top)
                        if len(pts) >= 3:
                            obstacles.append(np.array(pts, dtype=np.int32))
                    elif "points" in obj:
                        pts = []
                        for p in obj["points"]:
                            pts.append([p["x"] * scale_x + left, p["y"] * scale_y + top])
                        if len(pts) >= 3:
                            obstacles.append(np.array(pts, dtype=np.int32))

            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.metric("Abanicos", len(fans))
            with col_info2:
                st.metric("Obstaculos", len(obstacles))

            if st.button("Generar Mapa de Calor", type="primary"):
                if len(fans) == 0:
                    st.warning("Dibuja al menos un abanico (circulo) antes de generar el mapa.")
                else:
                    with st.spinner("Calculando colisiones y flujo..."):
                        sim_w = max(w // resolution, 1)
                        sim_h = max(h // resolution, 1)

                        obstacle_mask = np.ones((sim_h, sim_w), dtype=np.uint8)
                        for poly in obstacles:
                            scaled_poly = (poly / resolution).astype(np.int32)
                            cv2.fillPoly(obstacle_mask, [scaled_poly], 0)

                        yy, xx = np.mgrid[0:sim_h, 0:sim_w]
                        total_intensity = np.zeros((sim_h, sim_w), dtype=np.float32)

                        progress_bar = st.progress(0)
                        for idx, fan in enumerate(fans):
                            fx = fan["x"] / resolution
                            fy = fan["y"] / resolution

                            dist = np.sqrt((xx - fx)**2 + (yy - fy)**2)

                            f_intensity = intensity_mult * np.exp(-global_decay * dist)

                            if use_los and len(obstacles) > 0:
                                num_samples = max(32, min(96, sim_w // 4))
                                vis = compute_visibility_sampled(fx, fy, sim_h, sim_w, obstacle_mask, num_samples=num_samples)
                                f_intensity *= vis
                            else:
                                f_intensity *= obstacle_mask

                            total_intensity += f_intensity
                            progress_bar.progress((idx + 1) / len(fans))

                        total_intensity *= obstacle_mask
                        progress_bar.empty()

                        fig, ax = plt.subplots(figsize=(10, h / w * 10))
                        ax.imshow(bg_image)
                        im = ax.imshow(
                            total_intensity, cmap='turbo', alpha=0.6,
                            extent=[0, w, h, 0], vmin=0,
                            vmax=max(np.max(total_intensity), 0.01)
                        )
                        ax.axis('off')
                        plt.colorbar(im, ax=ax, label="Intensidad de flujo")

                        st.pyplot(fig)

                        st.subheader("Exportar")
                        col_exp1, col_exp2 = st.columns(2)

                        with col_exp1:
                            buf = io.BytesIO()
                            fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
                            st.download_button("Descargar Imagen (PNG)", buf.getvalue(), "mapa_calor.png", "image/png")

                        with col_exp2:
                            df = pd.DataFrame(total_intensity)
                            csv = df.to_csv(index=False)
                            st.download_button("Descargar Datos (CSV)", csv, "datos_flujo.csv", "text/csv")

                        plt.close(fig)

    else:
        st.info("Bienvenid@. Sube una imagen de plano en el panel izquierdo para comenzar.")


if __name__ == "__main__":
    main()
