import streamlit as st
import os
import json
from PIL import Image

from utils.auth import get_current_user
from utils.db import (
    get_proyectos_by_admin,
    get_all_proyectos,
    get_proyecto,
    update_proyecto,
    delete_proyecto,
    get_users_by_role,
    asignar_proyecto_a_cliente,
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
            has_lineas = proy.get("ruta_lineas_corriente") and os.path.exists(proy["ruta_lineas_corriente"])
            has_lateral = proy.get("ruta_vista_lateral") and os.path.exists(proy["ruta_vista_lateral"])
            has_resultado = proy.get("imagen_resultado") and os.path.exists(proy["imagen_resultado"])

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
                        st.image(img, caption="Imagen original", use_container_width=True)
                    else:
                        st.write("Sin imagen disponible.")
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
                    st.image(img, caption="Imagen original", use_container_width=True)
                else:
                    st.write("Sin imagen disponible.")

            info_col, dl_col = st.columns([1, 1])

            with info_col:
                st.write(f"**Creado por:** {proy.get('admin_name', 'N/A')}")
                st.write(f"**Asignado a:** {proy.get('cliente_name', 'Sin asignar')}")
                st.write(f"**Fecha:** {proy['fecha']}")

                if proy.get("parametros"):
                    try:
                        params = json.loads(proy["parametros"])
                        st.write(f"**Temp. Ambiente:** {params.get('temp_ambiente', 'N/A')} C")
                        st.write(f"**Velocidad:** {params.get('velocidad', 'N/A')}")
                        st.write(f"**Sens. Termica:** {params.get('sensacion_termica', 'N/A')} C")
                    except (json.JSONDecodeError, TypeError):
                        pass

            with dl_col:
                if has_resultado:
                    with open(proy["imagen_resultado"], "rb") as f:
                        st.download_button(
                            "Descargar Mapa de Calor",
                            f.read(),
                            f"{proy['nombre']}_mapa.png",
                            "image/png",
                            key=f"dl_img_{proy['id']}",
                        )

                if has_lineas:
                    with open(proy["ruta_lineas_corriente"], "rb") as f:
                        st.download_button(
                            "Descargar Flujo de Aire",
                            f.read(),
                            f"{proy['nombre']}_lineas.png",
                            "image/png",
                            key=f"dl_lineas_{proy['id']}",
                        )

                if has_lateral:
                    with open(proy["ruta_vista_lateral"], "rb") as f:
                        st.download_button(
                            "Descargar Vista Lateral",
                            f.read(),
                            f"{proy['nombre']}_lateral.png",
                            "image/png",
                            key=f"dl_lateral_{proy['id']}",
                        )

                if proy.get("datos_csv") and os.path.exists(proy["datos_csv"]):
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
                asignar_proyecto_a_cliente(proy_id, opts[sel_idx]["id"])
                st.toast("Asignacion guardada.")

            st.selectbox(
                "Asignar a cliente",
                range(len(opciones)),
                index=current_idx,
                format_func=lambda i: opciones[i]["username"],
                key=f"asignar_{proy['id']}",
                on_change=_on_asignar_change,
            )

            confirm_key = f"confirm_del_{proy['id']}"
            if confirm_key not in st.session_state:
                st.session_state[confirm_key] = False

            if not st.session_state[confirm_key]:
                if st.button("Eliminar proyecto", key=f"del_proy_{proy['id']}", type="secondary"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                st.warning("Estas seguro de que quieres eliminar este proyecto? Esta accion no se puede deshacer.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Si, eliminar", key=f"yes_del_{proy['id']}", type="primary"):
                        del st.session_state[confirm_key]
                        delete_proyecto(proy["id"])
                        st.success("Proyecto eliminado.")
                        st.rerun()
                with col_no:
                    if st.button("Cancelar", key=f"no_del_{proy['id']}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
