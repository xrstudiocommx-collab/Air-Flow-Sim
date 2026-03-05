# Simulador de Flujo de Aire Arquitectónico

## Overview
A Streamlit-based architectural airflow simulator. Users can upload floor plan images, draw fans (circles) and obstacles (polygons) on the canvas, generate a heatmap showing exponential air flow decay that respects obstacle collisions, and export results as PNG or CSV.

## Tech Stack
- **Framework**: Streamlit
- **Libraries**: NumPy, OpenCV (headless), Pillow, matplotlib, pandas, streamlit-drawable-canvas
- **Language**: Python

## Project Structure
- `app.py` — Main Streamlit application with all simulation logic

## How It Works
1. User uploads a floor plan image (PNG/JPG)
2. User draws circles (fans) and polygons (obstacles) on an interactive canvas
3. Simulation calculates exponential decay airflow from each fan
4. Obstacles block airflow using OpenCV polygon masking
5. Results displayed as a heatmap overlay on the floor plan
6. Export options: PNG image or CSV data

## Running
The workflow runs: `streamlit run app.py --server.port 5000 --server.address 0.0.0.0`
