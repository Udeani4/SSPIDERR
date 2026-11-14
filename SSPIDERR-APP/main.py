"""Development entry point:  python main.py

Set FLASK_DEBUG=1 for auto-reload and debug pages (never in production, S4).
For production on Windows use:  python serve.py
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", threaded=True)
