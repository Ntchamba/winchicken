"""Business logic for the finance app, kept out of views.py per this project's "thin views"
convention (see docs/architecture.md).
"""
from django.db.models import Sum

from apps.finance.models import SalaryPayment, SalaryPaymentStatus, WorkHoursEntry


def calculate_salaries(farm, month, year):
    """(Re)computes a PENDING `SalaryPayment` per farm employee with an `hourly_rate` set, for
    the given calendar month — on-demand only (2026-08-27, Salaires module). This project has no
    Celery Beat schedule configured anywhere (`config/celery.py` has no `beat_schedule` — a
    pre-existing, already-documented gap, see docs/deviations.md), so "automatically at
    month-end" isn't realistically available without adding that infrastructure from scratch,
    which is well beyond this task's own scope; an explicit "Calculer les salaires du mois"
    action is also consistent with every other consequential action in this app (task
    assignment, purchase-order receiving, case resolution, ...) being an explicit user action,
    not a silent background one.

    Never touches an already-PAID payment for that period — `total_hours`/
    `hourly_rate_snapshot`/`amount` are deliberate snapshots (see `SalaryPayment`'s own
    docstring), so recalculating after a payment is marked PAID must not silently change it. A
    still-PENDING row for that period *is* overwritten with the latest totals, so correcting a
    `WorkHoursEntry` before payment is reflected on the next calculation.

    Returns the list of `SalaryPayment` rows created/updated this call — an already-PAID row for
    the period is left untouched and not included.
    """
    from apps.core.models import User

    updated = []
    employees = User.objects.filter(farm=farm, hourly_rate__isnull=False)
    for employee in employees:
        total_hours = WorkHoursEntry.objects.filter(
            user=employee, date__year=year, date__month=month,
        ).aggregate(total=Sum('hours_worked'))['total'] or 0

        existing = SalaryPayment.objects.filter(user=employee, period_month=month, period_year=year).first()
        if existing and existing.status == SalaryPaymentStatus.PAID:
            continue

        payment, _ = SalaryPayment.objects.update_or_create(
            user=employee, period_month=month, period_year=year,
            defaults={
                'farm': farm,
                'total_hours': total_hours,
                'hourly_rate_snapshot': employee.hourly_rate,
                'amount': total_hours * employee.hourly_rate,
                'status': SalaryPaymentStatus.PENDING,
            },
        )
        updated.append(payment)
    return updated
