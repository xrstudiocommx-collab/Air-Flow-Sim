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

    cols = st.columns(2)
    for i, proy in enumerate(proyectos):
        with cols[i % 2]:
            st.subheader(proy["nombre"])
            st.caption(f"Fecha: {proy['fecha'][:10]} | Ingeniero: {proy.get('admin_name', 'N/A')}")

            if proy["imagen_resultado"] and os.path.exists(proy["imagen_resultado"]):
                img = Image.open(proy["imagen_resultado"])
                st.image(img, caption="Mapa de calor", use_container_width=True)
            elif proy["imagen_original"] and os.path.exists(proy["imagen_original"]):
                img = Image.open(proy["imagen_original"])
                st.image(img, caption="Plano original", use_container_width=True)
            else:
                st.write("Sin imagen.")

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                if proy["imagen_resultado"] and os.path.exists(proy["imagen_resultado"]):
                    with open(proy["imagen_resultado"], "rb") as f:
                        st.download_button(
                            "Descargar Imagen",
                            f.read(),
                            f"{proy['nombre']}.png",
                            "image/png",
                            key=f"cli_img_{proy['id']}",
                        )
            with col_d2:
                if proy["datos_csv"] and os.path.exists(proy["datos_csv"]):
                    with open(proy["datos_csv"], "r") as f:
                        st.download_button(
                            "Descargar CSV",
                            f.read(),
                            f"{proy['nombre']}.csv",
                            "text/csv",
                            key=f"cli_csv_{proy['id']}",
                        )

            st.divider()
