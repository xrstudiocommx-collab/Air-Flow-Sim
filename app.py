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
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] h1,
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] h2,
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] h3,
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] h4,
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] p,
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] span,
    [data-testid="stSidebar"] > div[data-testid="stSidebarContent"] label,
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stCaption {
        color: #1a1a2e !important;
    }
    [data-testid="stHeader"] {
        background-color: #F5F7FA !important;
    }
    [data-testid="stMainBlockContainer"] h1,
    [data-testid="stMainBlockContainer"] h2,
    [data-testid="stMainBlockContainer"] h3,
    [data-testid="stMainBlockContainer"] h4,
    [data-testid="stMainBlockContainer"] p,
    [data-testid="stMainBlockContainer"] span,
    [data-testid="stMainBlockContainer"] label {
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
        background-color: #FFFFFF !important;
    }
    .stButton > button:hover {
        background-color: #F0F0F0 !important;
        border-color: #AAA !important;
    }
    .stButton > button[kind="primary"] {
        color: white !important;
        background-color: #4FC3F7 !important;
        border-color: #4FC3F7 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #3BAEE0 !important;
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
    div[data-baseweb="input"] input {
        color: #1a1a2e !important;
    }
    .stCaption, .stCaption * {
        color: #666 !important;
    }
    hr {
        border-color: #E0E0E0 !important;
    }
    .stSlider [data-baseweb="slider"] div[role="slider"] {
        background-color: #4FC3F7 !important;
    }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span,
    [data-testid="stNotification"] p,
    [data-testid="stNotification"] span {
        color: inherit !important;
    }
    [data-testid="stFileUploader"] label,
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] p {
        color: #1a1a2e !important;
    }
    [data-testid="stFileUploader"] section {
        background-color: #FFFFFF !important;
        border-color: #CCC !important;
    }
    div[data-testid="stFileUploader"] button {
        color: #FFFFFF !important;
        background-color: #000000 !important;
    }
    div[data-testid="stFileUploader"] button p,
    div[data-testid="stFileUploader"] button span {
        color: #FFFFFF !important;
    }
    div[data-testid="stForm"] button {
        color: #FFFFFF !important;
        background-color: #000000 !important;
    }
    div[data-testid="stForm"] button p,
    div[data-testid="stForm"] button span {
        color: #FFFFFF !important;
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
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label {
        color: #E0E0E0 !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #2A2A3E !important;
        color: #E0E0E0 !important;
        border-color: #444 !important;
    }
    div[data-baseweb="input"] > div {
        background-color: #2A2A3E !important;
        color: #E0E0E0 !important;
    }
    div[data-baseweb="input"] input {
        color: #E0E0E0 !important;
    }
    [data-testid="stForm"] {
        background-color: #2A2A3E !important;
        border: 1px solid #444 !important;
    }
    .stButton > button {
        color: #E0E0E0 !important;
        border-color: #555 !important;
    }
    .stButton > button:hover {
        background-color: #3A3A4E !important;
        border-color: #777 !important;
    }
    .stButton > button[kind="primary"] {
        color: white !important;
        background-color: #4FC3F7 !important;
        border-color: #4FC3F7 !important;
    }
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span,
    [data-testid="stNotification"] p,
    [data-testid="stNotification"] span {
        color: inherit !important;
    }
    hr {
        border-color: #444 !important;
    }
</style>
"""

HIDE_SIDEBAR_CSS = """
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    button[kind="headerNoPadding"] { display: none !important; }
</style>
"""


def apply_theme():
    theme = st.session_state.get("app_theme", "Oscuro")
    if theme == "Claro":
        st.markdown(LIGHT_THEME_CSS, unsafe_allow_html=True)
    else:
        st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)


def _get_logo_path():
    theme = st.session_state.get("app_theme", "Oscuro")
    if theme == "Oscuro":
        return "static/kale_logo_white.png"
    return "static/kale_logo_original.png"


def _render_theme_toggle(key_suffix=""):
    current_theme = st.session_state.get("app_theme", "Oscuro")
    if current_theme == "Oscuro":
        icono = "☀️"
        tooltip = "Cambiar a modo claro"
    else:
        icono = "🌙"
        tooltip = "Cambiar a modo oscuro"

    col1, col2, col3 = st.columns([8, 1, 1])
    with col3:
        if st.button(icono, key=f"theme_toggle_{key_suffix}", help=tooltip):
            st.session_state["app_theme"] = "Claro" if current_theme == "Oscuro" else "Oscuro"
            st.rerun()


def show_login():
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)
    apply_theme()
    _render_theme_toggle("login")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image(_get_logo_path(), width=380)
        st.markdown(
            "<p style='opacity:0.7; font-size:0.95rem; margin-top:0; margin-bottom:1rem;'>"
            "Simulador de Flujo de Aire — Sistema de simulacion sobre planos arquitectonicos</p>",
            unsafe_allow_html=True,
        )

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


def show_app():
    apply_theme()
    _render_theme_toggle("app")

    user = get_current_user()
    role = get_current_role()

    with st.sidebar:
        st.image(_get_logo_path(), width=180)
        st.markdown(f"### Bienvenido, {user['username']}")
        st.caption(f"Rol: {role}")
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
            "Navegacion",
            menu_options,
            index=0,
            format_func=lambda x: f"{menu_icons[menu_options.index(x)]} {x}",
            label_visibility="collapsed",
        )

        st.divider()

    if selection == "Simulador":
        from views.simulador import render
        render()
    elif selection == "Proyectos":
        from views.proyectos import render
        render()
    elif selection == "Usuarios":
        from views.usuarios import render
        render()
    elif selection == "Mis Planos":
        from views.mis_planos import render
        render()

    if selection != "Simulador":
        with st.sidebar:
            st.divider()
            if st.button("Cerrar Sesion", use_container_width=True):
                logout()
                st.rerun()


if is_logged_in():
    show_app()
else:
    show_login()
