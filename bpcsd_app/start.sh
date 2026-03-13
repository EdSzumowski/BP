#!/bin/bash
cd /workspace/bpcsd_app
VENV=/workspace/bpcsd_app/venv
if [ ! -f "$VENV/bin/python3" ]; then
    python3 -m venv $VENV
fi
$VENV/bin/pip install streamlit pdfplumber reportlab pandas --quiet 2>/dev/null
$VENV/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false 2>&1
