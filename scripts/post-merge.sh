#!/bin/bash
set -e
# Python/Streamlit project — install any new Python dependencies if file exists
if [ -f requirements.txt ]; then
  pip install -r requirements.txt --quiet
fi
