import streamlit as st
import os
from PIL import Image

from utils.auth import get_current_user
from utils.db import get_proyectos_by_cliente


def render():
    user = get_current_user()
    if not user or user["role"] != "cliente":
        st.error("Acceso denegado.")
        return

    st.title("Mis Planos")

    proyectos = get_proyectos_by_cliente(user["id"])

    if not proyectos:
        st.info("Aun no tienes proyectos asignados. Contacta a tu administrador.")
        return

    for proy in proyectos:
        st.subheader(proy["nombre"])
        st.caption(f"Fecha: {proy['fecha'][:10]} | Ingeniero: {proy.get('admin_name', 'N/A')}")

        has_resultado = proy.get("imagen_resultado") and os.path.exists(proy["imagen_resultado"])
        has_lineas = proy.get("ruta_lineas_corriente") and os.path.exists(proy["ruta_lineas_corriente"])
        has_lateral = proy.get("ruta_vista_lateral") and os.path.exists(proy["ruta_vista_lateral"])

        tab_names = ["Vista Superior"]
        if has_lineas:
            tab_names.append("Flujo de Aire")
        if has_lateral:
            tab_names.append("Vista Lateral")

        if len(tab_names) > 1:
            tabs = st.tabs(tab_names)
            tab_idx = 0

            with tabs[tab_idx]:
                if has_resultado:
                    img = Image.open(proy["imagen_resultado"])
                    st.image(img, caption="Mapa de calor", use_container_width=True)
                elif proy.get("imagen_original") and os.path.exists(proy["imagen_original"]):
                    img = Image.open(proy["imagen_original"])
                    st.image(img, caption="Plano original", use_container_width=True)
                else:
                    st.write("Sin imagen.")
            tab_idx += 1

            if has_lineas:
                with tabs[tab_idx]:
                    img_l = Image.open(proy["ruta_lineas_corriente"])
                    st.image(img_l, caption="Lineas de corriente", use_container_width=True)
                tab_idx += 1

            if has_lateral:
                with tabs[tab_idx]:
                    img_lat = Image.open(proy["ruta_vista_lateral"])
                    st.image(img_lat, caption="Vista lateral (elevacion)", use_container_width=True)
        else:
            if has_resultado:
                img = Image.open(proy["imagen_resultado"])
                st.image(img, caption="Mapa de calor", use_container_width=True)
            elif proy.get("imagen_original") and os.path.exists(proy["imagen_original"]):
                img = Image.open(proy["imagen_original"])
                st.image(img, caption="Plano original", use_container_width=True)
            else:
                st.write("Sin imagen.")

        dl_cols = st.columns(4)
        with dl_cols[0]:
            if has_resultado:
                with open(proy["imagen_resultado"], "rb") as f:
                    st.download_button(
                        "Descargar Mapa",
                        f.read(),
                        f"{proy['nombre']}_mapa.png",
                        "image/png",
                        key=f"cli_img_{proy['id']}",
                    )
        with dl_cols[1]:
            if has_lineas:
                with open(proy["ruta_lineas_corriente"], "rb") as f:
                    st.download_button(
                        "Descargar Flujo",
                        f.read(),
                        f"{proy['nombre']}_lineas.png",
                        "image/png",
                        key=f"cli_lineas_{proy['id']}",
                    )
        with dl_cols[2]:
            if has_lateral:
                with open(proy["ruta_vista_lateral"], "rb") as f:
                    st.download_button(
                        "Descargar Lateral",
                        f.read(),
                        f"{proy['nombre']}_lateral.png",
                        "image/png",
                        key=f"cli_lateral_{proy['id']}",
                    )
        with dl_cols[3]:
            if proy.get("datos_csv") and os.path.exists(proy["datos_csv"]):
                with open(proy["datos_csv"], "r") as f:
                    st.download_button(
                        "Descargar CSV",
                        f.read(),
                        f"{proy['nombre']}.csv",
                        "text/csv",
                        key=f"cli_csv_{proy['id']}",
                    )

        st.divider()
