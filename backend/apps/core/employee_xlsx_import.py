"""Excel import for Employees — update-or-create by Email (docs/excel-import.md).

NEVER deletes a `User` absent from the file. For a matched account it updates Nom / Rôle /
Civilité / Taux horaire and **never touches the password** (no password column is read for an
existing match). A new account needs a password to exist, so one is generated and returned in
the summary, once, for the admin to hand off. Role is validated strictly against the real
`UserRole` values (French labels also accepted) — a bad role skips the row with a clear reason.
"""
import secrets

from django.db import transaction

from apps.core.models import ROLE_PROFILE_MODELS, Civility, User, UserRole, create_role_profile
from apps.core.serializers import EmployeeSerializer
from apps.core.xlsx import (
    WorkbookError, as_number, build_workbook, cell_getter, clean, header_index, open_rows, require_headers,
)

HEADERS = ['Nom', 'Email', 'Rôle', 'Civilité', 'Taux horaire']
_ALIASES = {'nom': 'name', 'email': 'email', 'rôle': 'role', 'role': 'role',
            'civilité': 'civility', 'civilite': 'civility', 'taux horaire': 'hourly_rate'}

# Accept the enum value OR its French label from EmployeesPage's ROLES list. ADMIN is not here
# on purpose — EmployeeSerializer.validate_role also rejects it (one admin per farm).
_ROLE_LABELS = {
    'fermier': UserRole.FARMER, 'ouvrier': UserRole.WORKER, 'technicien': UserRole.TECHNICIAN,
    'caissier': UserRole.CASHIER, 'administrateur secondaire': UserRole.SECONDARY_ADMIN,
    'gérant de ferme': UserRole.FARM_MANAGER, 'gerant de ferme': UserRole.FARM_MANAGER,
}
_ROLE_BY_TEXT = {**_ROLE_LABELS, **{r.value.lower(): r.value for r in UserRole if r != UserRole.ADMIN}}
_VALID_ROLE_HINT = 'Rôles acceptés : Fermier, Ouvrier, Technicien, Caissier, Gérant de ferme, Administrateur secondaire.'

_CIVILITY_BY_TEXT = {
    'm': Civility.M, 'm.': Civility.M, 'monsieur': Civility.M,
    'mme': Civility.MME, 'mme.': Civility.MME, 'madame': Civility.MME,
}

EXAMPLE_ROWS = [
    ['Marie Dupont', 'marie.dupont@example.com', 'Fermier', 'Mme', 1200],
    ['Jean Kouassi', 'jean.kouassi@example.com', 'Gérant de ferme', 'M.', ''],
]


def build_employee_template() -> bytes:
    return build_workbook('Employés', HEADERS, EXAMPLE_ROWS)


def _generate_temp_password() -> str:
    return secrets.token_urlsafe(9)  # ~12 URL-safe chars


def check_employee_workbook(file_obj) -> None:
    """Raise WorkbookError now for a file the import could not use at all (unreadable, empty,
    missing headers), so the upload is refused at once instead of failing later in the
    background job. The same `_read_workbook` the import runs."""
    _read_workbook(file_obj)
    file_obj.seek(0)


def _read_workbook(file_obj):
    header, rows_iter = open_rows(file_obj)
    index = header_index(header, _ALIASES)
    require_headers(index, [('Nom', 'name'), ('Email', 'email'), ('Rôle', 'role')])
    return index, rows_iter


def parse_and_apply_employee_import(actor, farm, file_obj, on_progress=None) -> dict:
    """`on_progress(done, total)`, when given, is called after every row: each new account
    hashes its password (~1 s), so a large file runs as a background job that reports how far
    it got (apps.core.import_jobs)."""
    index, rows_iter = _read_workbook(file_obj)
    get = cell_getter(index)
    rows = list(rows_iter)
    total = len(rows)

    updated = created = 0
    skipped = []
    new_accounts = []  # [{line, name, email, password}]

    for line, raw in enumerate(rows, start=2):
        if on_progress is not None:
            on_progress(line - 2, total)
        if raw is None or all(clean(c) == '' for c in raw):
            continue

        name = clean(get(raw, 'name'))
        email = clean(get(raw, 'email'))
        role_raw = clean(get(raw, 'role'))
        if not name:
            skipped.append({'line': line, 'reason': 'nom manquant'})
            continue
        if not email:
            skipped.append({'line': line, 'reason': 'email manquant'})
            continue
        role = _ROLE_BY_TEXT.get(role_raw.lower())
        if role is None:
            skipped.append({'line': line, 'reason': f'rôle invalide : « {role_raw or "(vide)"} ». {_VALID_ROLE_HINT}'})
            continue

        civility = _CIVILITY_BY_TEXT.get(clean(get(raw, 'civility')).lower(), Civility.M)
        rate = as_number(get(raw, 'hourly_rate'))

        try:
            with transaction.atomic():
                existing = User.objects.filter(farm=farm, email__iexact=email).first()
                if existing:
                    old_role = existing.role
                    ser = EmployeeSerializer(
                        existing, data={'name': name, 'role': role, 'civility': civility},
                        partial=True, context={'farm': farm},
                    )
                    ser.is_valid(raise_exception=True)
                    ser.save()
                    if role != old_role:
                        # Swap the class-table-inheritance subtype row (Admin/Farmer/Worker/…).
                        ROLE_PROFILE_MODELS[old_role].objects.filter(user=existing).delete()
                        create_role_profile(existing)
                    if rate is not None:
                        existing.hourly_rate = rate  # same field EmployeeHourlyRateView sets
                        existing.save(update_fields=['hourly_rate'])
                    updated += 1
                else:
                    temp_password = _generate_temp_password()
                    ser = EmployeeSerializer(
                        data={'name': name, 'email': email, 'role': role,
                              'civility': civility, 'password': temp_password},
                        context={'farm': farm},
                    )
                    ser.is_valid(raise_exception=True)
                    user = ser.save()
                    if rate is not None:
                        user.hourly_rate = rate
                        user.save(update_fields=['hourly_rate'])
                    created += 1
                    new_accounts.append({'line': line, 'name': name, 'email': email, 'password': temp_password})
        except Exception as exc:
            skipped.append({'line': line, 'reason': _reason(exc)})

    if on_progress is not None:
        on_progress(total, total)
    return {'updated': updated, 'created': created, 'skipped': skipped, 'newAccounts': new_accounts}


def _reason(exc):
    detail = getattr(exc, 'detail', None)
    if isinstance(detail, dict):
        first = next(iter(detail.values()))
        return str(first[0] if isinstance(first, list) else first)
    if isinstance(detail, list):
        return str(detail[0])
    return str(exc) or 'ligne invalide'
