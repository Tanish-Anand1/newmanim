from __future__ import annotations

import os

from rq import SimpleWorker, Worker

from app.models import init_db
from app.rq_queue import generation_queue, redis_connection


def main() -> None:
    init_db()
    queue = generation_queue()
    # RQ's Worker depends on Unix process APIs. On Windows each SimpleWorker
    # is an isolated process; production concurrency comes from several worker
    # processes. Linux containers retain RQ's regular timeout-capable Worker.
    worker_type = SimpleWorker if os.name == "nt" else Worker
    worker_type([queue], connection=redis_connection()).work(with_scheduler=True)


if __name__ == "__main__":
    main()
