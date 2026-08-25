from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.models import ContactMessage, Farm, NewsletterSubscriber, User
from apps.core.permissions import IsAdminOrSecondaryAdmin
from apps.core.serializers import (
    ContactMessageSerializer,
    EmployeeSerializer,
    FarmCreateSerializer,
    MeSerializer,
    WinchickenTokenObtainPairSerializer,
)


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


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/"""

    permission_classes = [permissions.AllowAny]
    serializer_class = WinchickenTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me/ — current user, role and onboarding `is_configured` flag."""

    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class EmployeeListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/employees/ — list/create employee accounts for the current farm.
    Creation reserved to Admin / Secondary Admin (section 8); listing allows any authenticated
    user of the farm. Excludes the requesting user's own account from the list."""

    serializer_class = EmployeeSerializer
    permission_classes = [IsAdminOrSecondaryAdmin]

    def get_queryset(self):
        return User.objects.filter(farm=self.request.user.farm).exclude(pk=self.request.user.pk)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['farm'] = self.request.user.farm
        return context


class EmployeeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/DELETE /api/employees/{id}/ — view, edit or remove one employee account.
    All three methods reserved to Admin / Secondary Admin (section 8)."""

    serializer_class = EmployeeSerializer
    permission_classes = [IsAdminOrSecondaryAdmin]
    lookup_field = 'pk'

    def get_queryset(self):
        return User.objects.filter(farm=self.request.user.farm)


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
