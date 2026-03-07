import streamlit as st

from utils.auth import get_current_user
from utils.db import get_all_users, create_user, update_user, delete_user


def render():
    user = get_current_user()
    if not user or user["role"] != "superadmin":
        st.error("Acceso denegado.")
        return

    st.title("Gestion de Usuarios")

    tab_list, tab_create = st.tabs(["Lista de Usuarios", "Crear Usuario"])

    with tab_list:
        users = get_all_users()
        if not users:
            st.info("No hay usuarios registrados.")
            return

        for u in users:
            with st.expander(f"{u['username']} — {u['role']}", expanded=False):
                col1, col2, col3 = st.columns(3)

                with col1:
                    new_username = st.text_input(
                        "Username", value=u["username"], key=f"uname_{u['id']}"
                    )

                with col2:
                    roles = ["superadmin", "admin", "cliente"]
                    new_role = st.selectbox(
                        "Rol",
                        roles,
                        index=roles.index(u["role"]),
                        key=f"role_{u['id']}",
                    )

                with col3:
                    new_pass = st.text_input(
                        "Nueva contrasena (dejar vacio para no cambiar)",
                        type="password",
                        key=f"pass_{u['id']}",
                    )

                st.caption(f"Creado: {u['created_at']}")

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Guardar cambios", key=f"save_{u['id']}"):
                        username_change = new_username if new_username != u["username"] else None
                        role_change = new_role if new_role != u["role"] else None
                        pass_change = new_pass if new_pass else None
                        ok, msg = update_user(u["id"], username_change, pass_change, role_change)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

                with col_b:
                    if u["id"] != user["id"]:
                        if st.button("Eliminar", key=f"del_{u['id']}", type="secondary"):
                            delete_user(u["id"])
                            st.success(f"Usuario '{u['username']}' eliminado.")
                            st.rerun()
                    else:
                        st.caption("(No puedes eliminarte a ti mismo)")

    with tab_create:
        with st.form("create_user_form"):
            st.subheader("Nuevo Usuario")
            new_user = st.text_input("Nombre de usuario")
            new_pw = st.text_input("Contrasena", type="password")
            new_role = st.selectbox("Rol", ["admin", "cliente", "superadmin"])
            submitted = st.form_submit_button("Crear Usuario")

            if submitted:
                if not new_user or not new_pw:
                    st.error("Completa todos los campos.")
                elif len(new_pw) < 3:
                    st.error("La contrasena debe tener al menos 3 caracteres.")
                else:
                    ok, msg = create_user(new_user, new_pw, new_role)
                    if ok:
                        st.session_state["user_created_msg"] = f"Usuario '{new_user}' creado exitosamente con rol '{new_role}'."
                        st.rerun()
                    else:
                        st.error(msg)

        if "user_created_msg" in st.session_state:
            st.success(st.session_state.pop("user_created_msg"))
