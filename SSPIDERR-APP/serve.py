"""Production server (works on Windows and on Render):  python serve.py

Uses waitress with several threads in ONE process. Keep it to one process:
the background scheduler and upload jobs run inside it.

Settings (environment variables):
  HOST / PORT        where to listen (Render sets PORT; use HOST=0.0.0.0 there)
  WAITRESS_THREADS   worker threads (default 8)
  TRUST_PROXY=1      the app sits behind a proxy that serves HTTPS (Render)
"""
import os

from waitress import serve

from app import create_app

app = create_app("production")

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    options = {"threads": int(os.environ.get("WAITRESS_THREADS", "8"))}
    if app.config.get("TRUST_PROXY"):
        # Waitress drops X-Forwarded-* headers from proxies it doesn't trust. On Render the only way in
        # is through Render's proxy, so trust it: links and cookies then use https://<your-app>.onrender.com.
        options.update(trusted_proxy="*", trusted_proxy_count=1,
                       trusted_proxy_headers="x-forwarded-for x-forwarded-proto x-forwarded-host",
                       clear_untrusted_proxy_headers=True)
    print(f"SSPIDERR running on http://{host}:{port}")
    serve(app, host=host, port=port, **options)
