"""Production server (works on Windows):  python serve.py

Uses waitress with several threads in ONE process. Keep it to one process:
the background scheduler and upload jobs run inside it.
"""
import os

from waitress import serve

from app import create_app

app = create_app("production")

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"SSPIDERR running on http://{host}:{port}")
    serve(app, host=host, port=port, threads=int(os.environ.get("WAITRESS_THREADS", "8")))
