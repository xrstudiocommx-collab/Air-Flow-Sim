# Simulador de Flujo de Aire Arquitectonico

## Overview
A Streamlit-based architectural airflow simulator with role-based authentication. Users can upload floor plans, draw fans and obstacles on an interactive canvas, simulate airflow with exponential decay and line-of-sight blocking, and export results.

## Tech Stack
- **Framework**: Streamlit (Python)
- **Database**: SQLite (users.db)
- **Auth**: bcrypt password hashing
- **Libraries**: NumPy, OpenCV (headless), Pillow, matplotlib, pandas, scipy, streamlit-drawable-canvas

## Project Structure
```
app.py                    # Main entry: login + navigation
pages/
  simulador.py            # Simulation page (admin/superadmin)
  proyectos.py            # Project management (admin/superadmin)
  mis_planos.py           # Client view (cliente role)
  usuarios.py             # User management (superadmin only)
utils/
  db.py                   # SQLite database operations
  auth.py                 # Authentication helpers
  simulation.py           # Airflow simulation engine (top-down)
  side_view.py            # Side-view (elevation) simulation engine
  streamlines.py          # Airflow streamline (flow lines) visualization
  canvas_utils.py         # Canvas object parsing
outputs/                  # Generated images and CSV files
.streamlit/config.toml    # Theme and server config
```

## Authentication & Roles
- **superadmin**: Full access (users, projects, simulator). Default: admin/admin
- **admin**: Simulator + project management
- **cliente**: View assigned projects only

## Simulation Features
- Circular fans (ceiling) with radial exponential decay
- Oval fans (pedestal/AirFree) with directional airflow along major axis
- Polygon obstacles with configurable transmission:
  - Obstaculo Chico (Ch): 80% flow transmission
  - Obstaculo Mediano (M): 50% flow transmission
  - Obstaculo Grande (G): 20% flow transmission
  - Pared (XL): 0% flow transmission (full block)
- Line-of-sight blocking with ray-traced visibility
- Resolution options: Baja (100x100), Media (200x200), Alta (400x400)
- Airflow streamlines visualization (top-down flow lines):
  - Toggle via checkbox in sidebar
  - Navy blue (#000080) fan origin markers on the streamlines figure
  - Colour gradient: navy blue (near fan) → green → transparent (far away)
  - Darker line appearance with exponential decay-based opacity
  - "Decaimiento líneas de corriente" slider (0.01–0.50) controls line reach
  - Lines deflect around obstacles following same shadow/blocking logic
  - Velocity field computed from fan positions and obstacle geometry
  - Exportable as separate PNG
- Export: PNG heatmap image + CSV with x,y,intensity data
- Side-view (elevation) visualization:
  - Toggle via checkbox in sidebar
  - Configurable ceiling height and pedestal fan height (meters)
  - Ceiling fans project downward jet, pedestal fans project horizontally
  - Same colormap and simulation parameters as top-down view
  - Exportable as separate PNG

## Running
Workflow: `streamlit run app.py --server.port 5000 --server.address 0.0.0.0`

## Theming
- Dark/Light toggle via CSS-injected button (top-right corner) using Sol/Luna icons
- Theme state: `st.session_state["app_theme"]` — "Oscuro" (dark) or "Claro" (light)
- Logos: KALE BLANCO (`static/kale_logo_white.png`) for Dark, KALE NEGRO (`static/kale_logo_original.png`) for Light
- All matplotlib figures (heatmap, streamlines, side view) use `_fig_bg`/`_fig_fg` variables for theme-aware rendering
- CSS themes: `DARK_THEME_CSS` and `LIGHT_THEME_CSS` in `app.py` with targeted selectors
- Base Streamlit theme in `config.toml` is "dark"; Light mode overrides via injected CSS

## Note
The streamlit-drawable-canvas library has a patched `__init__.py` to fix compatibility with newer Streamlit versions (base64 image encoding instead of removed `image_to_url`).
