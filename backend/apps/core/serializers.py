from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.models import AuditLogEntry, Civility, ContactMessage, Farm, User, UserRole, create_role_profile
from apps.core.services import is_farm_configured


def _blacklist_all_tokens(user):
    """Blacklist every outstanding refresh token for `user` (security review 2026-09-26,
    MEDIUM-5). Imported lazily-safe at module load: token_blacklist is in INSTALLED_APPS."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)

# Namespaced salt + short TTL for the pre-login reset step-up token (see PreLoginResetRequestSerializer).
# `django.core.signing` is HMAC-SHA256 over SECRET_KEY — no DB row, no session, self-expiring.
PRELOGIN_RESET_SALT = 'apps.core.prelogin-farm-reset'
PRELOGIN_RESET_MAX_AGE = 300  # seconds — the visitor must get through both steps inside 5 minutes


class FarmCreateSerializer(serializers.Serializer):
    """POST /api/farm/create/ payload — creates the single Farm row and its Admin account together.

    Rejected with 409 by the view (not this serializer) once a Farm already exists, since the
    whole deployment is single-farm.
    """

    admin_name = serializers.CharField(max_length=255, help_text='Full name of the administrator account being created.')
    civility = serializers.ChoiceField(choices=Civility.choices, help_text='Monsieur / Madame — used to personalize task-reminder SMS.')
    email = serializers.EmailField(help_text='Login email for the new administrator; must be unique across all users.')
    password = serializers.CharField(write_only=True, help_text='Minimum 8 characters (Django AUTH_PASSWORD_VALIDATORS).')
    farm_name = serializers.CharField(max_length=255, help_text='Display name for the farm (Farm.name).')

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Un compte utilise déjà cet email.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        with transaction.atomic():
            farm = Farm.objects.create(name=validated_data['farm_name'])
            user = User.objects.create_user(
                email=validated_data['email'],
                password=validated_data['password'],
                name=validated_data['admin_name'],
                civility=validated_data['civility'],
                role=UserRole.ADMIN,
                farm=farm,
            )
            create_role_profile(user)
        return user


class EmployeeSerializer(serializers.ModelSerializer):
    """GET/POST/PUT payload for /api/employees/ and /api/employees/{id}/ (section 8 role management).

    `role` cannot be ADMIN — there is exactly one administrator per farm, created via
    FarmCreateSerializer, never through this endpoint.
    """

    password = serializers.CharField(
        write_only=True, required=False,
        help_text='Required on create; optional on update (leave blank to keep the current password).',
    )

    class Meta:
        model = User
        fields = ['id', 'name', 'civility', 'email', 'phone', 'role', 'password', 'is_active', 'hourly_rate']
        # hourly_rate is read-only here — it's edited through the dedicated
        # EmployeeHourlyRateView (2026-08-27, Salaires module Part D), not this general-purpose
        # create/update endpoint, so a PUT here never accidentally clobbers a payroll rate.
        read_only_fields = ['id', 'hourly_rate']
        extra_kwargs = {
            'civility': {'required': True},
            # The model's UniqueValidator ran before validate_email and answered with Django's
            # "Un objet user avec ce champ email existe déjà."; validate_email is the check
            # (case-insensitive, with the app's own sentence).
            'email': {'validators': []},
        }

    def validate_role(self, value):
        if value == UserRole.ADMIN:
            raise serializers.ValidationError("Les comptes administrateur ne peuvent pas être créés depuis ce point d'accès.")
        return value

    def validate_email(self, value):
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Un compte utilise déjà cet email.')
        return value

    def validate_password(self, value):
        # Every non-admin account is created/edited here, and this path never checked password
        # strength — a worker could be given the password "1" (security review 2026-09-26,
        # MEDIUM-3). FarmCreateSerializer already runs the same Django validators for the admin;
        # `password` is optional on update, so an empty/omitted value skips this and keeps the
        # current one (see update()). The generated import temp-password (~12 url-safe chars)
        # passes these validators, so bulk import is unaffected.
        validate_password(value)
        return value

    def create(self, validated_data):
        farm = self.context['farm']
        password = validated_data.pop('password')
        with transaction.atomic():
            user = User.objects.create_user(farm=farm, **validated_data, password=password)
            create_role_profile(user)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        if password:
            # A changed password must end the account's other live sessions, or a stolen or
            # shared token keeps working for its full 7 days (security review 2026-09-26,
            # MEDIUM-5). Blacklist every refresh token issued to this user so far; access tokens
            # already expire within 30 min. Only tokens minted since token_blacklist was
            # installed are tracked — older ones simply age out.
            _blacklist_all_tokens(instance)
        return instance


class EmployeePayrollSerializer(serializers.ModelSerializer):
    """GET /api/employees/payroll/ response (2026-08-27, Salaires module Part D) — the narrow
    id/name/hourly_rate read backing SalairesSection.jsx's rate-editing list for Farm Manager,
    who has no access to the full EmployeeSerializer-backed /api/employees/ endpoint. Read-only:
    edits go through EmployeeHourlyRateView's PATCH, not this serializer."""

    class Meta:
        model = User
        fields = ['id', 'name', 'hourly_rate']
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    """GET /api/auth/me/ response — used by the frontend AuthContext to drive the onboarding gate.

    `is_configured` mirrors `apps.core.services.is_farm_configured`: it drives
    `ProtectedRoute`'s redirect to /onboarding/protocol on the frontend.
    """

    is_configured = serializers.SerializerMethodField(
        help_text='True once the farm has >=1 house with a protocol and >=1 stock item (see services.is_farm_configured).'
    )
    farm = serializers.IntegerField(source='farm_id', read_only=True, help_text='Farm.id — always the same single farm row.')
    farm_name = serializers.CharField(source='farm.name', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'role', 'farm', 'farm_name', 'is_configured']

    def get_is_configured(self, user) -> bool:
        if not user.farm_id:
            return False
        return is_farm_configured(user.farm)


class WinchickenTokenObtainPairSerializer(TokenObtainPairSerializer):
    """POST /api/auth/login/ — standard SimpleJWT pair, extended with `is_configured` and `role`
    so the frontend can route straight to onboarding or the dashboard without a second request.
    """

    username_field = User.USERNAME_FIELD

    def validate(self, attrs):
        data = super().validate(attrs)
        data['is_configured'] = is_farm_configured(self.user.farm) if self.user.farm_id else False
        data['role'] = self.user.role
        return data


class FarmResetSerializer(serializers.Serializer):
    """POST /api/farm/reset/ payload — the re-authentication step of the factory-reset flow.

    `password` is checked against the *authenticated* caller's own hash (`request.user`, from
    `context['request']`, never a user id/email in the payload) — re-entering someone else's
    password isn't a thing this endpoint could even be tricked into checking.
    """

    password = serializers.CharField(write_only=True, help_text='The current Administrateur\'s own password, re-entered.')

    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Mot de passe incorrect.')
        return value


class PreLoginResetRequestSerializer(serializers.Serializer):
    """POST /api/farm/reset/request/ payload — step 1 of the *unauthenticated* factory-reset
    flow reachable from `/login` (distinct from `FarmResetSerializer`, which needs a live
    session). Verifies the supplied email + password belong to a real `UserRole.ADMIN` account
    on the single farm, and hands back a short-lived signed token (not a login session) that
    step 2 (`PreLoginResetConfirmSerializer`) exchanges for the actual wipe.

    Every failure — unknown email, wrong password, valid credentials for a non-Administrateur —
    raises the exact same `'invalid'` error, so an unauthenticated visitor learns nothing about
    which accounts exist or what role they hold. The dummy `set_password` on the unknown-email
    path keeps response timing from leaking existence either (mirrors Django's own
    `ModelBackend.authenticate`).
    """

    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True)

    default_error_messages = {'invalid': 'Identifiants invalides.'}

    def validate(self, attrs):
        user = User.objects.select_related('farm').filter(email__iexact=attrs['email']).first()
        if user is not None and user.check_password(attrs['password']) \
                and user.role == UserRole.ADMIN and user.farm_id is not None:
            attrs['user'] = user
            return attrs
        if user is None:
            User().set_password(attrs['password'])  # equalize timing for the unknown-email path
        self.fail('invalid')

    def build_token(self):
        return signing.dumps({'uid': self.validated_data['user'].id}, salt=PRELOGIN_RESET_SALT)


class PreLoginResetConfirmSerializer(serializers.Serializer):
    """POST /api/farm/reset/confirm/ payload — step 2 of the unauthenticated flow. Re-opens the
    token from step 1 (rejecting a tampered, foreign-salt, or >5-min-old token), re-checks the
    account is still an existing `UserRole.ADMIN`, and requires the exact `Farm.name` typed back
    — the same "prove it, twice" bar as the in-dashboard `FactoryResetModal`, minus the
    password (already proven in step 1). `validated_data['user']` is then passed straight to
    `apps.core.services.factory_reset_farm` as the audit actor.
    """

    token = serializers.CharField(write_only=True)
    farm_name = serializers.CharField(write_only=True)

    default_error_messages = {
        'invalid_token': 'Session de réinitialisation expirée. Recommencez depuis la connexion.',
        'name_mismatch': 'Le nom de la ferme ne correspond pas.',
    }

    def validate(self, attrs):
        try:
            payload = signing.loads(attrs['token'], salt=PRELOGIN_RESET_SALT, max_age=PRELOGIN_RESET_MAX_AGE)
        except signing.BadSignature:  # covers SignatureExpired too
            self.fail('invalid_token')
        user = User.objects.select_related('farm').filter(id=payload.get('uid'), role=UserRole.ADMIN).first()
        if user is None or user.farm is None:
            self.fail('invalid_token')
        if attrs['farm_name'] != user.farm.name:
            self.fail('name_mismatch')
        attrs['user'] = user
        return attrs


class AuditLogEntrySerializer(serializers.ModelSerializer):
    """GET /api/audit-log/ response row — read-only, see `apps.core.views.AuditLogListView`."""

    class Meta:
        model = AuditLogEntry
        fields = ['id', 'user_name_snapshot', 'action', 'target_description', 'timestamp']
        read_only_fields = fields


class ContactMessageSerializer(serializers.ModelSerializer):
    """Schema-only representation of the public landing-page contact form.

    `ContactMessageView.create()` validates and saves the row itself (a manual required-fields
    check) rather than calling this serializer — it exists so drf-spectacular can document the
    request/response shape; keep its fields in sync with that view if the form changes.
    """

    class Meta:
        model = ContactMessage
        fields = ['full_name', 'email', 'phone', 'subject', 'message']
