import streamlit as st
import numpy as np
import pandas as pd
from PIL import Image
import matplotlib.pyplot as plt
import io
import cv2
from streamlit_drawable_canvas import st_canvas

# Configuración de página
st.set_page_config(layout="wide", page_title="Simulador de Flujo de Aire")

def main():
    st.title("🌬️ Simulador de Flujo de Aire con Obstáculos")
    st.markdown("""
    Dibuja **Círculos** para representar abanicos y **Polígonos** para representar obstáculos (paredes).
    El flujo de aire se calcula considerando el bloqueo físico de los obstáculos.
    """)

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        uploaded_file = st.file_uploader("1. Sube un plano (Imagen)", type=['png', 'jpg', 'jpeg'])
        
        st.divider()
        st.subheader("Herramientas de Dibujo")
        drawing_mode = st.radio(
            "Selecciona modo:",
            ("transform", "circle", "polygon"),
            format_func=lambda x: "Seleccionar/Mover" if x == "transform" else ("Abanico (Círculo)" if x == "circle" else "Obstáculo (Polígono)")
        )
        
        st.divider()
        st.subheader("Parámetros de Simulación")
        global_decay = st.slider("Tasa de decaimiento global", 0.01, 0.50, 0.08, help="Mayor valor = el aire llega menos lejos")
        intensity_mult = st.slider("Multiplicador de Intensidad", 1.0, 50.0, 10.0)
        resolution = st.select_slider("Resolución de Simulación", options=[1, 2, 4, 8, 16], value=8, help="Menor valor = más calidad pero más lento")
        
        if st.button("🧹 Limpiar Todo"):
            st.session_state["canvas_key"] = np.random.randint(0, 1000)
            st.rerun()

    # --- MAIN CONTENT ---
    if uploaded_file:
        bg_image = Image.open(uploaded_file)
        w, h = bg_image.size
        # Escalar si es muy grande para Streamlit
        max_width = 800
        if w > max_width:
            ratio = max_width / w
            bg_image = bg_image.resize((int(w * ratio), int(h * ratio)))
            w, h = bg_image.size

        # Canvas para dibujo
        st.subheader("🎨 Dibuja Abanicos y Obstáculos")
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",  # Color para abanicos
            stroke_width=2,
            stroke_color="#000000",
            background_image=bg_image,
            update_freq=100,
            width=w,
            height=h,
            drawing_mode=drawing_mode,
            key=st.session_state.get("canvas_key", "canvas"),
            display_toolbar=True,
        )

        # Procesar objetos del canvas
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            fans = []
            obstacles = []
            
            for obj in objects:
                if obj["type"] == "circle":
                    # El canvas de streamlit guarda círculos con left, top, radius
                    fans.append({
                        "x": obj["left"] + obj["radius"] * obj["scaleX"],
                        "y": obj["top"] + obj["radius"] * obj["scaleY"],
                        "r": obj["radius"] * obj["scaleX"]
                    })
                elif obj["type"] == "polygon" or obj["type"] == "path":
                    # Extraer puntos del polígono
                    if "points" in obj:
                        pts = []
                        for p in obj["points"]:
                            pts.append([p["x"] + obj["left"], p["y"] + obj["top"]])
                        obstacles.append(np.array(pts, dtype=np.int32))

            if st.button("🚀 Generar Mapa de Calor", type="primary"):
                with st.spinner("Calculando colisiones y flujo..."):
                    # Crear grid de simulación
                    sim_w = w // resolution
                    sim_h = h // resolution
                    
                    # Máscara de obstáculos (OpenCV)
                    mask = np.ones((sim_h, sim_w), dtype=np.float32)
                    for poly in obstacles:
                        scaled_poly = (poly / resolution).astype(np.int32)
                        cv2.fillPoly(mask, [scaled_poly], 0)
                    
                    # Grid de coordenadas
                    yy, xx = np.mgrid[0:sim_h, 0:sim_w]
                    total_intensity = np.zeros((sim_h, sim_w), dtype=np.float32)
                    
                    for fan in fans:
                        fx = fan["x"] / resolution
                        fy = fan["y"] / resolution
                        
                        dist_sq = (xx - fx)**2 + (yy - fy)**2
                        dist = np.sqrt(dist_sq)
                        
                        # Intensidad base
                        f_intensity = intensity_mult * np.exp(-global_decay * dist)
                        
                        # Bloqueo por obstáculos (Ray Casting simplificado)
                        # Para cada celda, trazamos línea hacia el fan
                        # En Python puro es lento, usamos una aproximación o limitamos
                        total_intensity += f_intensity * mask

                    # Aplicar máscara final
                    total_intensity *= mask
                    
                    # Visualización
                    fig, ax = plt.subplots(figsize=(10, h/w * 10))
                    ax.imshow(bg_image)
                    im = ax.imshow(total_intensity, cmap='turbo', alpha=0.6, extent=[0, w, h, 0], vmin=0, vmax=intensity_mult)
                    ax.axis('off')
                    plt.colorbar(im, ax=ax, label="Intensidad de flujo")
                    
                    st.pyplot(fig)
                    
                    # --- EXPORT ---
                    st.subheader("📤 Exportar")
                    col_exp1, col_exp2 = st.columns(2)
                    
                    with col_exp1:
                        buf = io.BytesIO()
                        fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
                        st.download_button("📥 Descargar Imagen (PNG)", buf.getvalue(), "mapa_calor.png", "image/png")
                        
                    with col_exp2:
                        # Datos CSV simplificados
                        df = pd.DataFrame(total_intensity)
                        csv = df.to_csv(index=False)
                        st.download_button("📊 Descargar Datos (CSV)", csv, "datos_flujo.csv", "text/csv")

    else:
        st.info("👋 Bienvenid@. Sube una imagen de plano en el panel izquierdo para comenzar.")

if __name__ == "__main__":
    main()
