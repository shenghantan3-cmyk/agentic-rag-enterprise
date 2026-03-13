from __future__ import annotations

import sys
from pathlib import Path

# Ensure `import core` and `import enterprise_api` work when running as a script.
_PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from rq import Connection, Worker

from enterprise_api.queue import get_redis_connection, get_queue_settings


def main() -> None:
    settings = get_queue_settings()
    conn = get_redis_connection()

    with Connection(conn):
        w = Worker([settings.queue_name])
        w.work(with_scheduler=False)


if __name__ == "__main__":
    main()
