from celery import shared_task


@shared_task
def deduct_daily_stock_consumption():
    """Celery Beat entry point (see `config.celery.app.conf.beat_schedule`, daily at midnight) —
    creates the day's automatic protocol-driven `OUT` StockMovement rows. Idempotent: safe to
    re-run the same day (see `apps.stock.services.run_daily_consumption`). Returns the number of
    movements created, for the task result log."""
    from apps.stock.services import run_daily_consumption

    created = run_daily_consumption()
    return len(created)
