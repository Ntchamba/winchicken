
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.models import AuditLogEntry, ContactMessage, Farm, NewsletterSubscriber, User
from apps.core.cache import cached_farm_response
from apps.core.overview import farm_overview
from apps.core.permissions import IsAdmin, IsAdminOrFarmManager, IsAdminOrSecondaryAdmin
from apps.core.serializers import (
    AuditLogEntrySerializer,
    ContactMessageSerializer,
    EmployeePayrollSerializer,
    EmployeeSerializer,
    FarmCreateSerializer,
    FarmResetSerializer,
    MeSerializer,
    PreLoginResetConfirmSerializer,
    PreLoginResetRequestSerializer,
    WinchickenTokenObtainPairSerializer,
)
from apps.core.services import InvalidHourlyRate, factory_reset_farm, parse_hourly_rate, record_audit_log


@extend_schema(
    responses=inline_serializer('HealthCheck', {'status': serializers.CharField()}),
    examples=[OpenApiExample('OK', value={'status': 'ok'})],
)
class HealthCheckView(APIView):
    """GET /api/health/ — public, used by the Docker `HEALTHCHECK` (not in the cahier des charges
    endpoint list; added purely for container orchestration)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'status': 'ok'})


@extend_schema(
    responses=inline_serializer('FarmExists', {'exists': serializers.BooleanField()}),
)
class FarmExistsView(APIView):
    """GET /api/farm/exists/ — public, tells the landing page whether to offer
    "Create the farm" or "Log in" (single-farm deployment: creation is closed once true)."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({'exists': Farm.objects.exists()})


class FarmCreateView(generics.CreateAPIView):
    """POST /api/farm/create/ — creates Farm + Admin User (+ Admin role-profile row) in one
    transaction and returns a JWT pair, exactly like /api/auth/login/ would right after.
    Rejected with 409 once a farm already exists (single-farm rule enforced server-side, not
    just hidden client-side).

    The `Farm.objects.exists()` check below is the fast common-case path (fails immediately,
    no write attempted) but is not by itself race-safe — two near-simultaneous requests could
    both pass it before either commits. `Farm.singleton_lock`'s DB-level unique constraint
    (core migration 0003) is what actually makes a second row impossible: the losing request's
    INSERT raises IntegrityError, caught below and turned into the same 409 rather than a 500."""

    permission_classes = [permissions.AllowAny]
    serializer_class = FarmCreateSerializer

    def create(self, request, *args, **kwargs):
        if Farm.objects.exists():
            return Response({'detail': 'Une ferme existe déjà pour cette installation.'}, status=status.HTTP_409_CONFLICT)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError:
            return Response({'detail': 'Une ferme existe déjà pour cette installation.'}, status=status.HTTP_409_CONFLICT)

        token_serializer = WinchickenTokenObtainPairSerializer(
            data={'email': user.email, 'password': request.data['password']}
        )
        token_serializer.is_valid(raise_exception=True)
        return Response(token_serializer.validated_data, status=status.HTTP_201_CREATED)


@extend_schema(
    request=FarmResetSerializer,
    responses={
        204: None,
        400: inline_serializer('FarmResetError', {'detail': serializers.CharField()}),
        403: inline_serializer('FarmResetForbidden', {'detail': serializers.CharField()}),
    },
    description=(
        'Administrateur-only, irreversible: wipes the Farm and every row that cascades from it '
        '(docs/deviations.md — the sanctioned exception to "no way to delete a farm").'
    ),
)
class FarmResetView(APIView):
    """POST /api/farm/reset/ — the sanctioned exception to this project's "no farm deletion" rule
    (docs/deviations.md Part 12). Administrateur-only (`IsAdmin`, checked server-side — a
    non-Administrateur caller gets 403 regardless of what the frontend shows/hides) and requires
    re-entering the caller's own current password (`FarmResetSerializer`, re-validated against
    the real password hash — never trusted from the frontend). The actual wipe
    (`apps.core.services.factory_reset_farm`) runs in one transaction: `Farm.objects.delete()`
    cascades to every farm-scoped table, including the caller's own `User` row, so there is no
    separate "log the caller out" step needed — see that function's docstring for why deleting
    the row is already enough to invalidate every issued JWT.
    """

    permission_classes = [IsAdmin]
    throttle_scope = 'farm_reset'  # security review 2026-09-26 HIGH-2

    def post(self, request):
        serializer = FarmResetSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        factory_reset_farm(request.user.farm, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    request=PreLoginResetRequestSerializer,
    responses={
        200: inline_serializer('PreLoginResetToken', {
            'token': serializers.CharField(), 'farm_name': serializers.CharField(),
        }),
        400: inline_serializer('PreLoginResetRequestError', {
            'non_field_errors': serializers.ListField(child=serializers.CharField()),
        }),
    },
    description=(
        'Step 1 of the unauthenticated farm-reset flow reachable from /login (no session). '
        'Verifies Administrateur email + password and returns a 5-minute signed token for step 2. '
        'Any failure returns the same generic "Identifiants invalides." — no account enumeration.'
    ),
)
class FarmResetRequestView(APIView):
    """POST /api/farm/reset/request/ — credential-gated entry point for resetting the farm
    *without* logging in (the in-dashboard `FarmResetView` above needs a live session; this one
    exists precisely for the case where nobody can). Publicly reachable (`AllowAny`); the
    Administrateur check lives entirely in `PreLoginResetRequestSerializer` and every failure
    mode collapses to one generic error so an anonymous caller can't probe accounts.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'farm_reset'  # security review 2026-09-26 HIGH-2: admin-password oracle

    def post(self, request):
        serializer = PreLoginResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'token': serializer.build_token(), 'farm_name': serializer.validated_data['user'].farm.name})


@extend_schema(
    request=PreLoginResetConfirmSerializer,
    responses={
        204: None,
        400: inline_serializer('PreLoginResetConfirmError', {
            'non_field_errors': serializers.ListField(child=serializers.CharField()),
        }),
    },
    description=(
        'Step 2 of the unauthenticated farm-reset flow: exchanges the step-1 token + the exact '
        'farm name for the irreversible wipe (same effect as POST /api/farm/reset/).'
    ),
)
class FarmResetConfirmView(APIView):
    """POST /api/farm/reset/confirm/ — consumes the step-1 token, re-verifies the account is an
    existing Administrateur, checks the typed-back `Farm.name`, then runs the same
    `apps.core.services.factory_reset_farm` the dashboard flow does. `AllowAny`: the token *is*
    the authorization.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = 'farm_reset'  # security review 2026-09-26 HIGH-2

    def post(self, request):
        serializer = PreLoginResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        factory_reset_farm(user.farm, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuditLogListView(generics.ListAPIView):
    """GET /api/audit-log/?action=&date_from=&date_to= — Administrateur only
    (docs/deviations.md Part 15). `action` filters to one exact code (e.g. "batch.deleted");
    `date_from`/`date_to` are inclusive `YYYY-MM-DD` bounds on the entry's date."""

    serializer_class = AuditLogEntrySerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = AuditLogEntry.objects.filter(farm=self.request.user.farm)
        action = self.request.query_params.get('action')
        if action:
            qs = qs.filter(action=action)
        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        return qs


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/"""

    permission_classes = [permissions.AllowAny]
    serializer_class = WinchickenTokenObtainPairSerializer
    throttle_scope = 'login'  # security review 2026-09-26 HIGH-2: brute-force limit, keyed by IP


class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me/ — current user, role and onboarding `is_configured` flag."""

    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class FarmOverviewView(APIView):
    """GET /api/farm/overview/ — the "Bilan global" tree: one core status plus the santé /
    finances / stock branches. Rules and thresholds live in `apps.core.overview`."""

    permission_classes = [permissions.IsAuthenticated]

    @cached_farm_response
    def get(self, request):
        if not request.user.farm_id:
            return Response({'detail': "Aucune ferme associée à ce compte."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(farm_overview(request.user.farm))


class EmployeeListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/employees/ — list/create employee accounts for the current farm.
    Creation reserved to Admin / Secondary Admin (section 8); listing allows any authenticated
    user of the farm. Excludes the requesting user's own account from the list."""

    serializer_class = EmployeeSerializer
    permission_classes = [IsAdminOrSecondaryAdmin]

    def get_queryset(self):
        # Ordered, because the list is paginated: an unordered query lets Postgres return rows in
        # any order per page, so an employee could appear on two pages and another on none.
        return User.objects.filter(farm=self.request.user.farm).exclude(pk=self.request.user.pk).order_by('name', 'id')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['farm'] = self.request.user.farm
        return context

    def perform_create(self, serializer):
        employee = serializer.save()
        record_audit_log(self.request.user, 'employee.created', f'{employee.name} ({employee.get_role_display()})')


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/DELETE /api/employees/{id}/ — view, edit or remove one employee account.
    All three methods reserved to Admin / Secondary Admin (section 8)."""

    serializer_class = EmployeeSerializer
    permission_classes = [IsAdminOrSecondaryAdmin]
    lookup_field = 'pk'

    def get_queryset(self):
        return User.objects.filter(farm=self.request.user.farm)

    def perform_update(self, serializer):
        employee = serializer.save()
        record_audit_log(self.request.user, 'employee.updated', f'{employee.name} ({employee.get_role_display()})')

    def perform_destroy(self, instance):
        record_audit_log(self.request.user, 'employee.deleted', f'{instance.name} ({instance.get_role_display()})')




class EmployeeHourlyRateView(APIView):
    """PATCH /api/employees/{id}/hourly-rate/ — Admin/Farm Manager (2026-08-27, Salaires module,
    Part D: "Administrateur sets/edits... Gérant de ferme can also edit it"). Deliberately a
    narrow, separate endpoint rather than widening `EmployeeDetailView`'s own
    `IsAdminOrSecondaryAdmin` to include Farm Manager — that would let Farm Manager edit an
    employee's role/password/email too, well beyond "manage payroll rates," which is all this
    task actually asked for."""

    permission_classes = [IsAdminOrFarmManager]

    def patch(self, request, pk):
        employee = get_object_or_404(User, pk=pk, farm=request.user.farm)
        try:
            employee.hourly_rate = parse_hourly_rate(request.data.get('hourly_rate'))
        except InvalidHourlyRate as exc:
            return Response({'hourly_rate': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        employee.save(update_fields=['hourly_rate'])
        return Response({'hourly_rate': employee.hourly_rate})


class EmployeePayrollListView(generics.ListAPIView):
    """GET /api/employees/payroll/ — Admin/Farm Manager only (2026-08-27, Salaires module Part D).
    A narrow id/name/hourly_rate read of every employee on the farm, used by
    SalairesSection.jsx's rate-editing list. Farm Manager has no visibility into the full
    Employees page (`canSeeEmployees` stays Admin/Secondary-Admin only, unchanged) — this is the
    equivalent read surface for the one thing Farm Manager is allowed to manage here: payroll
    rates. Deliberately excludes email/phone/role/is_active — not a general employee list, and
    editing still goes through the separate EmployeeHourlyRateView PATCH above, not this view."""

    serializer_class = EmployeePayrollSerializer
    permission_classes = [IsAdminOrFarmManager]

    def get_queryset(self):
        return User.objects.filter(farm=self.request.user.farm).exclude(pk=self.request.user.pk).order_by('name')


@extend_schema(
    request=ContactMessageSerializer,
    responses={
        201: inline_serializer('ContactMessageCreated', {'detail': serializers.CharField()}),
        400: inline_serializer('ContactMessageError', {'detail': serializers.CharField()}),
    },
)
class ContactMessageView(generics.CreateAPIView):
    """POST /api/contact/ — public landing-page contact form (implementation-detail spec 1.3;
    absent from the cahier des charges endpoint list). Validates required fields manually
    (full_name, email, subject, message) rather than through `ContactMessageSerializer`, which
    is declared purely for schema documentation — keep the two in sync if the form changes."""

    permission_classes = [permissions.AllowAny]
    queryset = ContactMessage.objects.none()
    serializer_class = ContactMessageSerializer

    def create(self, request, *args, **kwargs):
        required = ['full_name', 'email', 'subject', 'message']
        missing = [f for f in required if not request.data.get(f)]
        if missing:
            return Response({'detail': f'Missing fields: {", ".join(missing)}'}, status=status.HTTP_400_BAD_REQUEST)
        ContactMessage.objects.create(
            full_name=request.data['full_name'],
            email=request.data['email'],
            phone=request.data.get('phone', ''),
            subject=request.data['subject'],
            message=request.data['message'],
        )
        return Response({'detail': 'Message received.'}, status=status.HTTP_201_CREATED)


@extend_schema(
    request=inline_serializer('NewsletterSubscribeRequest', {'email': serializers.EmailField()}),
    responses={
        201: inline_serializer('NewsletterSubscribed', {'detail': serializers.CharField()}),
        400: inline_serializer('NewsletterError', {'detail': serializers.CharField()}),
    },
)
class NewsletterSubscribeView(APIView):
    """POST /api/newsletter/ — public landing-page newsletter opt-in (implementation-detail spec
    1.3; absent from the cahier des charges endpoint list). Idempotent: re-subscribing an
    already-known email is a no-op (`get_or_create`), not an error."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        NewsletterSubscriber.objects.get_or_create(email=email)
        return Response({'detail': 'Subscribed.'}, status=status.HTTP_201_CREATED)


class EmployeeImportTemplateView(APIView):
    """GET /api/employees/import-template.xlsx — ready-to-fill Employees import template.
    AllowAny (static example content) so it can be a plain download link."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.core.employee_xlsx_import import build_employee_template
        from apps.core.xlsx import xlsx_download
        return xlsx_download(build_employee_template(), 'modele-employes.xlsx')


class EmployeeImportView(APIView):
    """POST /api/employees/import-xlsx/ (multipart, field `file`) — update-or-create employee
    accounts by Email. Never deletes; never resets an existing account's password. New accounts
    get a generated temporary password, returned once in `newAccounts`. Admin / Secondary Admin.

    Runs in the background since 2026-09-25 (apps.core.import_jobs): an unusable file is still
    refused here with 400, otherwise 202 with `{jobId, status, processed, total}`; poll
    `GET /api/employees/import-xlsx/{jobId}/` until `status` is `done` (then `result` holds
    {updated, created, skipped:[{line, reason}], newAccounts:[{line, name, email, password}]})
    or `error` (`detail`).
    """

    permission_classes = [IsAdminOrSecondaryAdmin]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = 'import'  # security review 2026-09-26 HIGH-2

    def post(self, request):
        from apps.core.import_jobs import start_employee_import
        from apps.core.xlsx import WorkbookError, check_upload_size

        upload = request.FILES.get('file')
        if upload is None:
            return Response({'detail': 'Aucun fichier reçu.'}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith('.xlsx'):
            return Response({'detail': 'Importez un fichier .xlsx (Excel).'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            check_upload_size(upload)  # security review 2026-09-26: refuse a memory bomb up front
            job = start_employee_import(request.user, upload)
        except WorkbookError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(job, status=status.HTTP_202_ACCEPTED)


class EmployeeImportJobView(APIView):
    """GET /api/employees/import-xlsx/{jobId}/ — progress, then the result, of a background
    employee import. DELETE forgets it (the result holds temporary passwords). Only the admin
    who started it can see it; anyone else gets 404."""

    permission_classes = [IsAdminOrSecondaryAdmin]

    def get(self, request, job_id):
        from apps.core.import_jobs import job_state

        state = job_state(job_id, request.user)
        if state is None:
            return Response({'detail': 'Import introuvable ou expiré.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(state)

    def delete(self, request, job_id):
        from apps.core.import_jobs import discard_job

        if not discard_job(job_id, request.user):
            return Response({'detail': 'Import introuvable ou expiré.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
