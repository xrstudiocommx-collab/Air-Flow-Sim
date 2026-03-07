import streamlit as st
from utils.db import init_db
from utils.auth import login_user, is_logged_in, get_current_user, get_current_role, logout

st.set_page_config(layout="wide", page_title="Simulador de Flujo de Aire", page_icon="🌀")

init_db()


def show_login():
    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0;">
            <h1>Simulador de Flujo de Aire</h1>
            <p style="color: #aaa; font-size: 1.1rem;">Sistema de simulacion de flujo de aire sobre planos arquitectonicos</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Iniciar Sesion")
            username = st.text_input("Usuario", placeholder="Ingresa tu usuario")
            password = st.text_input("Contrasena", type="password", placeholder="Ingresa tu contrasena")
            submitted = st.form_submit_button("Entrar", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("Completa ambos campos.")
                else:
                    user = login_user(username, password)
                    if user:
                        st.session_state["user"] = {
                            "id": user["id"],
                            "username": user["username"],
                            "role": user["role"],
                        }
                        st.rerun()
                    else:
                        st.error("Usuario o contrasena incorrectos.")

        st.caption("Credenciales por defecto: admin / admin (superadmin)")


def show_app():
    user = get_current_user()
    role = get_current_role()

    with st.sidebar:
        st.markdown(f"**Usuario:** {user['username']}")
        st.markdown(f"**Rol:** {role}")
        st.divider()

        if role == "superadmin":
            menu_options = ["Simulador", "Proyectos", "Usuarios"]
            menu_icons = ["🌀", "📁", "👥"]
        elif role == "admin":
            menu_options = ["Simulador", "Proyectos"]
            menu_icons = ["🌀", "📁"]
        else:
            menu_options = ["Mis Planos"]
            menu_icons = ["📂"]

        selection = st.radio(
            "Menu",
            menu_options,
            format_func=lambda x: f"{menu_icons[menu_options.index(x)]} {x}",
            label_visibility="collapsed",
        )

        st.divider()
        if st.button("Cerrar Sesion", use_container_width=True):
            logout()
            st.rerun()

    if selection == "Simulador":
        from pages.simulador import render
        render()
    elif selection == "Proyectos":
        from pages.proyectos import render
        render()
    elif selection == "Usuarios":
        from pages.usuarios import render
        render()
    elif selection == "Mis Planos":
        from pages.mis_planos import render
        render()


if is_logged_in():
    show_app()
else:
    show_login()
