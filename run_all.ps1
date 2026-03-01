# 1) avvia ingest seriale
Start-Process -NoNewWindow python -ArgumentList "serial_reader.py"

# 2) avvia API
uvicorn api:app --host 0.0.0.0 --port 8000