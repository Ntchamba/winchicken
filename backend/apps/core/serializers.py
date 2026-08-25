from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.models import ContactMessage, Farm, User, UserRole, create_role_profile
from apps.core.services import is_farm_configured


class FarmCreateSerializer(serializers.Serializer):
    """POST /api/farm/create/ payload — creates the single Farm row and its Admin account together.

    Rejected with 409 by the view (not this serializer) once a Farm already exists, since the
    whole deployment is single-farm.
    """

    admin_name = serializers.CharField(max_length=255, help_text='Full name of the administrator account being created.')
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
        fields = ['id', 'name', 'email', 'phone', 'role', 'password', 'is_active']
        read_only_fields = ['id']

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
        return instance


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


class ContactMessageSerializer(serializers.ModelSerializer):
    """Schema-only representation of the public landing-page contact form.

    `ContactMessageView.create()` validates and saves the row itself (a manual required-fields
    check) rather than calling this serializer — it exists so drf-spectacular can document the
    request/response shape; keep its fields in sync with that view if the form changes.
    """

    class Meta:
        model = ContactMessage
        fields = ['full_name', 'email', 'phone', 'subject', 'message']
