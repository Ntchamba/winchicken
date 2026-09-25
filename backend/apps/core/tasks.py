from celery import shared_task


@shared_task
def run_employee_import(job_id: str, actor_id: int):
    """Background employee Excel import — see apps.core.import_jobs. IDs only: the file and the
    job state are in the cache under `job_id`."""
    from apps.core.import_jobs import run_job

    run_job(job_id, actor_id)
