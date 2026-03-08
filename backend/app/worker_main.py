"""RQ worker - listens to priority queues, crawler on low_priority."""
from rq import Worker, Queue, Connection
from redis import Redis

from app.config import get_config


def main():
    config = get_config()
    redis_url = config["settings"].redis_url
    redis_conn = Redis.from_url(redis_url)
    queues = [
        Queue("high_priority", connection=redis_conn),
        Queue("normal_priority", connection=redis_conn),
        Queue("low_priority", connection=redis_conn),
    ]
    with Connection(redis_conn):
        worker = Worker(queues)
        worker.work()


if __name__ == "__main__":
    main()
