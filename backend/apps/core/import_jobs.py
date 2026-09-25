"""Employee Excel import as a background job (2026-09-25).

Every new account hashes a generated password, about a second each: a 100-row file took 107 s
in the request, and above ~80 rows gunicorn's 120 s timeout killed the worker mid-import — the
accounts created so far existed, but the temporary passwords shown only in the response were
lost. The upload is now checked at once (headers), stored, and imported by a Celery task that
reports progress; the screen polls `job_state`.

State lives in the Django cache (the stack's Redis, shared by web and worker), never in a
table: the result carries the temporary passwords, and it is kept only `RESULT_TTL`, readable
only by the admin who started the import, and deleted as soon as they close it. The result is
stored encrypted (Fernet, key derived from SECRET_KEY): Redis snapshots its memory to disk, and
the passwords must not sit there in clear.
"""
import base64
import hashlib
import json
import logging
import uuid

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

FILE_TTL = 60 * 60
RESULT_TTL = 24 * 60 * 60


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(f'employee-import-result:{settings.SECRET_KEY}'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _seal(result):
    return _fernet().encrypt(json.dumps(result).encode()).decode()


def _unseal(token):
    return json.loads(_fernet().decrypt(token.encode()))


def _state_key(job_id):
    return f'employee-import:{job_id}:state'


def _file_key(job_id):
    return f'employee-import:{job_id}:file'


def start_employee_import(actor, upload) -> dict:
    """Check the file, store it, queue the import. Raises WorkbookError for an unusable file."""
    from apps.core.employee_xlsx_import import check_employee_workbook
    from apps.core.tasks import run_employee_import

    check_employee_workbook(upload)
    job_id = uuid.uuid4().hex
    cache.set(_file_key(job_id), upload.read(), FILE_TTL)
    state = {'jobId': job_id, 'status': 'queued', 'processed': 0, 'total': None, 'ownerId': actor.id}
    cache.set(_state_key(job_id), state, RESULT_TTL)
    run_employee_import.delay(job_id, actor.id)
    return job_state(job_id, actor) or state


def job_state(job_id, actor):
    """The job as the screen sees it, or None when it does not exist, expired, or belongs to
    someone else (the result holds passwords)."""
    state = cache.get(_state_key(job_id))
    if not state or state.get('ownerId') != actor.id:
        return None
    visible = {key: value for key, value in state.items() if key not in ('ownerId', 'sealedResult')}
    if 'sealedResult' in state:
        visible['result'] = _unseal(state['sealedResult'])
    return visible


def discard_job(job_id, actor) -> bool:
    if job_state(job_id, actor) is None:
        return False
    cache.delete_many([_state_key(job_id), _file_key(job_id)])
    return True


def _update(job_id, **changes):
    state = cache.get(_state_key(job_id)) or {'jobId': job_id}
    state.update(changes)
    cache.set(_state_key(job_id), state, RESULT_TTL)


def run_job(job_id, actor_id) -> None:
    """The Celery task's body. Every outcome ends in a state the screen can show."""
    from io import BytesIO

    from apps.core.employee_xlsx_import import parse_and_apply_employee_import
    from apps.core.models import User
    from apps.core.services import record_audit_log
    from apps.core.xlsx import WorkbookError

    data = cache.get(_file_key(job_id))
    actor = User.objects.filter(pk=actor_id).select_related('farm').first()
    if data is None or actor is None:
        _update(job_id, status='error', detail="Le fichier importé n'est plus disponible. Relancez l'import.")
        return
    _update(job_id, status='running')

    def progress(done, total):
        _update(job_id, processed=done, total=total)

    try:
        result = parse_and_apply_employee_import(actor, actor.farm, BytesIO(data), on_progress=progress)
    except WorkbookError as exc:
        _update(job_id, status='error', detail=str(exc))
        return
    except Exception:
        logger.exception('Employee import job %s failed', job_id)
        _update(job_id, status='error', detail="L'import s'est interrompu. Les comptes déjà créés sont conservés.")
        return
    finally:
        cache.delete(_file_key(job_id))
    record_audit_log(
        actor, 'employee.imported',
        f"Import employés ({result['updated']} maj, {result['created']} créé(s))",
    )
    _update(job_id, status='done', sealedResult=_seal(result))
