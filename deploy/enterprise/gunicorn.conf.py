bind = "0.0.0.0:8000"

# Concurrency: set WEB_CONCURRENCY to tune. Default in compose: 2
workers = int(__import__("os").environ.get("WEB_CONCURRENCY", "2"))

worker_class = "uvicorn.workers.UvicornWorker"

# If you see timeouts during long RAG runs, increase this.
timeout = int(__import__("os").environ.get("GUNICORN_TIMEOUT", "180"))

accesslog = "-"
errorlog = "-"
loglevel = __import__("os").environ.get("LOG_LEVEL", "info").lower()

# Keep worker recycling conservative
max_requests = int(__import__("os").environ.get("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = int(__import__("os").environ.get("GUNICORN_MAX_REQUESTS_JITTER", "0"))
