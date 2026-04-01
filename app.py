import streamlit as st
import base64
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


def _load_icon_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


_SOL_B64 = _load_icon_base64("static/icon_sol.png")
_LUNA_B64 = _load_icon_base64("static/icon_luna.png")

THEME_TOGGLE_FIXED_CSS = """
<style>
    .theme-toggle-fixed {{
        position: fixed;
        top: 4px;
        right: 8px;
        z-index: 999999;
    }}
    .theme-toggle-fixed .stButton {{
        width: 32px !important;
        height: 32px !important;
    }}
    .theme-toggle-fixed button {{
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
        min-height: 32px !important;
        max-height: 32px !important;
        width: 32px !important;
        max-width: 32px !important;
        cursor: pointer !important;
        box-shadow: none !important;
        overflow: visible !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}
    .theme-toggle-fixed button:hover {{
        opacity: 0.7 !important;
        background: transparent !important;
    }}
    .theme-toggle-fixed button:active,
    .theme-toggle-fixed button:focus {{
        box-shadow: none !important;
        outline: none !important;
        background: transparent !important;
    }}
    .theme-toggle-fixed button p {{
        display: none !important;
    }}
    .theme-toggle-fixed button::before {{
        content: "";
        display: block;
        width: 22px;
        height: 22px;
        min-width: 22px;
        min-height: 22px;
        background-image: url("data:image/png;base64,{icon_b64}");
        background-size: contain;
        background-repeat: no-repeat;
        background-position: center;
    }}
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


def _render_theme_toggle_fixed(key_suffix=""):
    current_theme = st.session_state.get("app_theme", "Oscuro")
    icon_b64 = _SOL_B64 if current_theme == "Oscuro" else _LUNA_B64
    st.markdown(
        THEME_TOGGLE_FIXED_CSS.format(icon_b64=icon_b64),
        unsafe_allow_html=True,
    )
    with st.container():
        st.markdown('<div class="theme-toggle-fixed">', unsafe_allow_html=True)
        if st.button(" ", key=f"theme_toggle_{key_suffix}"):
            st.session_state["app_theme"] = "Claro" if current_theme == "Oscuro" else "Oscuro"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


def show_login():
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)
    apply_theme()
    _render_theme_toggle_fixed("login")

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
    _render_theme_toggle_fixed("app")

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
