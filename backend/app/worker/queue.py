import logging

from redis import Redis
from rq import Queue
from rq.command import send_stop_job_command
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus

from app.core.config import get_settings

log = logging.getLogger(__name__)

ANALYSIS_QUEUE = "analysis"
CATALOG_QUEUE = "catalog"


def analysis_queue() -> Queue:
    return Queue(ANALYSIS_QUEUE, connection=Redis.from_url(get_settings().redis_url))


def catalog_queue() -> Queue:
    """Adds shows to the catalogue and completes them (see worker/catalog.py); its own queue so
    a long intro/outro analysis never holds it up."""
    return Queue(CATALOG_QUEUE, connection=Redis.from_url(get_settings().redis_url))


def timeout_seconds() -> int:
    return max(60, round(get_settings().analysis_timeout_minutes * 60))


def timeout_message() -> str:
    minutes = get_settings().analysis_timeout_minutes
    unit = "minute" if minutes == 1 else "minutes"
    return f"Stopped after {minutes:g} {unit} (ANALYSIS_TIMEOUT_MINUTES)"


def stop_job(job_id: str) -> None:
    """Take a job out of the queue, or kill the worker process running it. Missing jobs (e.g.
    lost when Redis restarted) are fine: there's nothing left to stop."""
    connection = analysis_queue().connection
    try:
        job = Job.fetch(job_id, connection=connection)
        if job.get_status() == JobStatus.STARTED:
            send_stop_job_command(connection, job_id)
        else:
            job.cancel()
    except NoSuchJobError:
        pass
    except Exception:
        log.warning("Could not stop analysis job %s in RQ", job_id, exc_info=True)
