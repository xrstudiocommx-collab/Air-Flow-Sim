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

HIDE_SIDEBAR_CSS = """
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    button[kind="headerNoPadding"] { display: none !important; }
</style>
"""

THEME_TOGGLE_CSS = """
<style>
    .theme-toggle-btn button {
        background: none !important;
        border: none !important;
        font-size: 1.6rem !important;
        padding: 0.2rem 0.5rem !important;
        cursor: pointer !important;
        min-height: 0 !important;
        line-height: 1 !important;
    }
    .theme-toggle-btn button:hover {
        opacity: 0.7 !important;
    }
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
    st.markdown(THEME_TOGGLE_CSS, unsafe_allow_html=True)
    current_theme = st.session_state.get("app_theme", "Oscuro")
    icon = "☀️" if current_theme == "Oscuro" else "🌙"
    with st.container():
        st.markdown('<div class="theme-toggle-btn">', unsafe_allow_html=True)
        if st.button(icon, key=f"theme_toggle_{key_suffix}", help="Cambiar tema"):
            st.session_state["app_theme"] = "Claro" if current_theme == "Oscuro" else "Oscuro"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


def show_login():
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)
    apply_theme()

    toggle_col, _ = st.columns([1, 11])
    with toggle_col:
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
        _render_theme_toggle("sidebar")
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
