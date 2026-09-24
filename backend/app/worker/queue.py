from redis import Redis
from rq import Queue

from app.core.config import get_settings

ANALYSIS_QUEUE = "analysis"


def analysis_queue() -> Queue:
    return Queue(ANALYSIS_QUEUE, connection=Redis.from_url(get_settings().redis_url))
