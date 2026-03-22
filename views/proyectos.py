import streamlit as st
import os
from PIL import Image

from utils.auth import get_current_user
from utils.db import (
    get_proyectos_by_admin,
    get_all_proyectos,
    get_proyecto,
    update_proyecto,
    delete_proyecto,
    get_users_by_role,
)


def render():
    user = get_current_user()
    if not user or user["role"] not in ("superadmin", "admin"):
        st.error("Acceso denegado.")
        return

    st.title("Gestion de Proyectos")

    if user["role"] == "superadmin":
        proyectos = get_all_proyectos()
    else:
        proyectos = get_proyectos_by_admin(user["id"])

    if not proyectos:
        st.info("No hay proyectos. Ve al Simulador para crear uno.")
        return

    for proy in proyectos:
        with st.expander(f"{proy['nombre']} — {proy['fecha'][:10]}", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                if proy["imagen_resultado"] and os.path.exists(proy["imagen_resultado"]):
                    img = Image.open(proy["imagen_resultado"])
                    st.image(img, caption="Resultado de simulacion", use_container_width=True)
                elif proy["imagen_original"] and os.path.exists(proy["imagen_original"]):
                    img = Image.open(proy["imagen_original"])
                    st.image(img, caption="Imagen original", use_container_width=True)
                else:
                    st.write("Sin imagen disponible.")

            with col2:
                st.write(f"**Creado por:** {proy.get('admin_name', 'N/A')}")
                st.write(f"**Asignado a:** {proy.get('cliente_name', 'Sin asignar')}")
                st.write(f"**Fecha:** {proy['fecha']}")

                if proy["imagen_resultado"] and os.path.exists(proy["imagen_resultado"]):
                    with open(proy["imagen_resultado"], "rb") as f:
                        st.download_button(
                            "Descargar Imagen",
                            f.read(),
                            f"{proy['nombre']}_resultado.png",
                            "image/png",
                            key=f"dl_img_{proy['id']}",
                        )

                if proy["datos_csv"] and os.path.exists(proy["datos_csv"]):
                    with open(proy["datos_csv"], "r") as f:
                        st.download_button(
                            "Descargar CSV",
                            f.read(),
                            f"{proy['nombre']}_datos.csv",
                            "text/csv",
                            key=f"dl_csv_{proy['id']}",
                        )

            st.divider()

            clientes = get_users_by_role("cliente")
            opciones = [{"id": None, "username": "-- Sin asignar --"}] + clientes

            current_idx = 0
            for i, c in enumerate(opciones):
                if c["id"] == proy["asignado_a"]:
                    current_idx = i
                    break

            def _on_asignar_change(proy_id=proy["id"], opts=opciones):
                sel_idx = st.session_state[f"asignar_{proy_id}"]
                update_proyecto(proy_id, asignado_a=opts[sel_idx]["id"])
                st.toast("Asignación guardada.", icon="✅")

            st.selectbox(
                "Asignar a cliente",
                range(len(opciones)),
                index=current_idx,
                format_func=lambda i: opciones[i]["username"],
                key=f"asignar_{proy['id']}",
                on_change=_on_asignar_change,
            )

            if st.button("Eliminar proyecto", key=f"del_proy_{proy['id']}", type="secondary"):
                delete_proyecto(proy["id"])
                st.success("Proyecto eliminado.")
                st.rerun()
