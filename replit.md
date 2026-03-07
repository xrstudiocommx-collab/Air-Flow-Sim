# Simulador de Flujo de Aire Arquitectonico

## Overview
A Streamlit-based architectural airflow simulator with role-based authentication. Users can upload floor plans, draw fans and obstacles on an interactive canvas, simulate airflow with exponential decay and line-of-sight blocking, and export results.

## Tech Stack
- **Framework**: Streamlit (Python)
- **Database**: SQLite (users.db)
- **Auth**: bcrypt password hashing
- **Libraries**: NumPy, OpenCV (headless), Pillow, matplotlib, pandas, streamlit-drawable-canvas

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
  simulation.py           # Airflow simulation engine
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
- Polygon obstacles with configurable transmission (Ch:80%, M:50%, G:20%, XL:0%)
- Line-of-sight blocking with ray-traced visibility
- Resolution options: Baja (100x100), Media (200x200), Alta (400x400)
- Export: PNG heatmap image + CSV with x,y,intensity data

## Running
Workflow: `streamlit run app.py --server.port 5000 --server.address 0.0.0.0`

## Note
The streamlit-drawable-canvas library has a patched `__init__.py` to fix compatibility with newer Streamlit versions (base64 image encoding instead of removed `image_to_url`).
