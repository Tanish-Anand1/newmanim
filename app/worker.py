from app.job_queue import run_worker


if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        pass
