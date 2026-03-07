import streamlit as st
from utils.db import init_db
from utils.auth import login_user, is_logged_in, get_current_user, get_current_role, logout

st.set_page_config(layout="wide", page_title="Simulador de Flujo de Aire", page_icon="🌀")

init_db()

LIGHT_THEME_CSS = """
<style>
    .stApp {
        background-color: #F5F7FA !important;
        color: #1a1a2e !important;
    }
    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E0E0E0 !important;
    }
    [data-testid="stSidebar"] * {
        color: #1a1a2e !important;
    }
    [data-testid="stHeader"] {
        background-color: #F5F7FA !important;
    }
    .stMarkdown, .stText, p, span, label, h1, h2, h3, h4, h5, h6 {
        color: #1a1a2e !important;
    }
    [data-testid="stMetricValue"],
    [data-testid="stMetricLabel"] {
        color: #1a1a2e !important;
    }
    .stSelectbox label, .stRadio label, .stSlider label, .stCheckbox label,
    .stTextInput label, .stNumberInput label {
        color: #1a1a2e !important;
    }
    [data-testid="stForm"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E0E0E0 !important;
    }
    .stButton > button {
        color: #1a1a2e !important;
        border-color: #CCC !important;
    }
    .stButton > button[kind="primary"] {
        color: white !important;
        background-color: #4FC3F7 !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #1a1a2e !important;
        border-color: #CCC !important;
    }
    div[data-baseweb="input"] > div {
        background-color: #FFFFFF !important;
        color: #1a1a2e !important;
    }
    .stCaption, .stCaption * {
        color: #666 !important;
    }
    hr {
        border-color: #E0E0E0 !important;
    }
</style>
"""

DARK_THEME_CSS = """
<style>
    .stApp {
        background-color: #1E1E2E !important;
        color: #E0E0E0 !important;
    }
    [data-testid="stSidebar"] {
        background-color: #2A2A3E !important;
    }
</style>
"""


def apply_theme():
    theme = st.session_state.get("app_theme", "Oscuro")
    if theme == "Claro":
        st.markdown(LIGHT_THEME_CSS, unsafe_allow_html=True)
    else:
        st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)


def show_login():
    apply_theme()

    st.markdown(
        """
        <div style="text-align: center; padding: 2rem 0;">
            <h1>Simulador de Flujo de Aire</h1>
            <p style="opacity: 0.7; font-size: 1.1rem;">Sistema de simulacion de flujo de aire sobre planos arquitectonicos</p>
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
    apply_theme()

    user = get_current_user()
    role = get_current_role()

    with st.sidebar:
        st.markdown(f"### Bienvenido, {user['username']}")
        st.caption(f"Rol: {role}")
        st.divider()

        if role == "superadmin":
            menu_options = ["Simulador", "Proyectos", "Usuarios"]
            menu_icons = ["🌀", "📁", "👥"]
            default_idx = 0
        elif role == "admin":
            menu_options = ["Simulador", "Proyectos"]
            menu_icons = ["🌀", "📁"]
            default_idx = 0
        else:
            menu_options = ["Mis Planos"]
            menu_icons = ["📂"]
            default_idx = 0

        selection = st.radio(
            "Navegacion",
            menu_options,
            index=default_idx,
            format_func=lambda x: f"{menu_icons[menu_options.index(x)]} {x}",
            label_visibility="collapsed",
        )

        st.divider()

        theme_options = ["Oscuro", "Claro"]
        current_theme = st.session_state.get("app_theme", "Oscuro")
        theme_idx = theme_options.index(current_theme) if current_theme in theme_options else 0
        new_theme = st.selectbox(
            "Tema",
            theme_options,
            index=theme_idx,
            format_func=lambda x: f"🌙 {x}" if x == "Oscuro" else f"☀️ {x}",
            key="theme_select",
        )
        if new_theme != st.session_state.get("app_theme", "Oscuro"):
            st.session_state["app_theme"] = new_theme
            st.rerun()

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
