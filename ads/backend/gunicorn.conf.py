import os

bind = "0.0.0.0:5000"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 120
preload_app = True  # migrations run once, in the master
worker_tmp_dir = "/dev/shm"
max_requests = 1000
max_requests_jitter = 100
reload = os.environ.get("GUNICORN_RELOAD") == "1"
if reload:
    preload_app = False


def post_fork(server, worker):
    import jobs
    jobs.start()
