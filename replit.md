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
  - Green fan origins with blue flow lines radiating outward
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

## Note
The streamlit-drawable-canvas library has a patched `__init__.py` to fix compatibility with newer Streamlit versions (base64 image encoding instead of removed `image_to_url`).
