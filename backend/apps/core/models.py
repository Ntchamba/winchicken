from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class Farm(models.Model):
    """Single-row root of the installation — one farm per deployment.

    `singleton_lock` is a fixed constant (always 1) with a unique DB constraint — this
    is the actual mechanism guaranteeing at most one Farm row can ever exist, including
    under a race condition where two POST /api/farm/create/ requests both pass the
    view's `Farm.objects.exists()` check before either commits. That check stays as the
    fast, friendly-error common path (returns 409 immediately, no DB round-trip needed
    to fail); this constraint is what makes a second row actually impossible — the
    losing request's INSERT raises IntegrityError, caught by the view and turned into
    the same 409 response rather than a 500."""

    singleton_lock = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    creation_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserRole(models.TextChoices):
    """The 7 account roles from the cahier des charges section 8 permission matrix.
    Drives both the class-table-inheritance subtype created alongside each User
    (see ROLE_PROFILE_MODELS below) and the `apps.core.permissions.role_permission` checks."""

    ADMIN = 'ADMIN', 'Admin'
    SECONDARY_ADMIN = 'SECONDARY_ADMIN', 'Secondary Admin'
    FARM_MANAGER = 'FARM_MANAGER', 'Farm Manager'
    FARMER = 'FARMER', 'Farmer'
    WORKER = 'WORKER', 'Worker'
    TECHNICIAN = 'TECHNICIAN', 'Technician'
    CASHIER = 'CASHIER', 'Cashier'


class UserManager(BaseUserManager):
    """Email-based user manager (no username field) — required because `User.USERNAME_FIELD = 'email'`."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN)
        return self._create_user(email, password, **extra_fields)


class Civility(models.TextChoices):
    """Used to personalize task-reminder SMS (apps.alerts.templates.render_task_reminder)."""

    M = 'M', 'Monsieur'
    MME = 'MME', 'Madame'


class User(AbstractBaseUser, PermissionsMixin):
    """Login account, whatever the role.

    `farm` is nullable only so the model can exist independently of a Farm at the DB level;
    in practice every User created through the API (FarmCreateSerializer / EmployeeSerializer)
    always gets a farm — there is no code path that leaves it null in normal use.
    Every User is expected to have exactly one matching role-subtype row (Admin, Farmer, ...,
    see ROLE_PROFILE_MODELS / create_role_profile below) selected by `role`.

    `civility` (2026-08-27) defaults to `M` so the migration backfills every pre-existing row to
    a concrete, non-null value instead of leaving old accounts unable to render a task-reminder
    SMS — see docs/deviations.md for why a default was chosen over a nullable field + login
    prompt. Both account-creation forms (FarmCreateSerializer, EmployeeSerializer) require it
    explicitly for every new account regardless of this model-level default.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True)
    civility = models.CharField(max_length=4, choices=Civility.choices, default=Civility.M)
    role = models.CharField(max_length=32, choices=UserRole.choices)
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Payroll rate (2026-08-27, Salaires module) — nullable: not every role is paid '
                   'hourly (e.g. Admin/Farm Manager), so no value is forced. Set from '
                   '/dashboard/employees by Admin/Farm Manager. A user with no rate set is '
                   'skipped by monthly salary calculation, not treated as a 0-rate employee.',
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'role']

    def __str__(self):
        return f'{self.name} ({self.role})'


# Role subtypes share their primary key with User (class-table inheritance):
# guarantees a single active role per account and avoids redundant generated ids.
# Matches the puml schema's `User ||--o| <Role> : specializes_as` relationships.

class Admin(models.Model):
    """Subtype row for role=ADMIN. Exactly one per farm in practice (created by FarmCreateView);
    nothing in the model layer enforces that uniqueness — it follows from there being only one
    signup endpoint that creates an ADMIN user."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='admin_profile')


class SecondaryAdmin(models.Model):
    """Subtype row for role=SECONDARY_ADMIN — oversees a set of Farmer accounts (see `Farmer.secondary_admin`)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='secondary_admin_profile')


class FarmManager(models.Model):
    """Subtype row for role=FARM_MANAGER. `admin` records which Admin supervises this manager
    (puml: `Admin ||--o{ FarmManager : supervises`); left null if not assigned."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='farm_manager_profile')
    admin = models.ForeignKey(Admin, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_farm_managers')


class Farmer(models.Model):
    """Subtype row for role=FARMER — the role responsible for a house/batch's daily protocol.
    `secondary_admin` records which SecondaryAdmin oversees this farmer
    (puml: `SecondaryAdmin ||--o{ Farmer : oversees`); left null if not assigned."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='farmer_profile')
    secondary_admin = models.ForeignKey(
        SecondaryAdmin, on_delete=models.SET_NULL, null=True, blank=True, related_name='overseen_farmers'
    )


class Worker(models.Model):
    """Subtype row for role=WORKER — can log DailyLog entries alongside Farmer/Admin/Farm
    Manager (see `apps.core.permissions.IsAdminOrFarmManagerOrFarmerOrWorker`)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='worker_profile')


class Technician(models.Model):
    """Subtype row for role=TECHNICIAN — handles EquipmentFault reports."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='technician_profile')


class Cashier(models.Model):
    """Subtype row for role=CASHIER — records Sale and PurchaseOrder rows."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='cashier_profile')


ROLE_PROFILE_MODELS = {
    UserRole.ADMIN: Admin,
    UserRole.SECONDARY_ADMIN: SecondaryAdmin,
    UserRole.FARM_MANAGER: FarmManager,
    UserRole.FARMER: Farmer,
    UserRole.WORKER: Worker,
    UserRole.TECHNICIAN: Technician,
    UserRole.CASHIER: Cashier,
}


def create_role_profile(user, **kwargs):
    """Creates the shared-PK subtype row matching user.role."""
    model = ROLE_PROFILE_MODELS[user.role]
    return model.objects.create(user=user, **kwargs)


class ContactMessage(models.Model):
    """Public landing-page contact form submission (implementation-detail 1.3)."""

    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    subject = models.CharField(max_length=64)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class NewsletterSubscriber(models.Model):
    """Public landing-page newsletter opt-in (implementation-detail 1.3) — not in the puml schema.
    `POST /api/newsletter/` is idempotent: subscribing twice with the same email is a no-op."""

    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLogEntry(models.Model):
    """Internal, in-database record of every consequential write action (2026-08-26,
    docs/deviations.md Part 15) — always written through `apps.core.services.record_audit_log`,
    never inline in a view. Deliberately farm-scoped and `on_delete=CASCADE`, so a factory reset
    wipes this table right along with everything else: this log covers "while the data still
    exists," not "after" — `apps.core.services.factory_reset_farm`'s plain-text external log
    file (outside the database) is what's left once this table itself is gone, and it's the one
    written for the reset event specifically for that reason.

    `user` is nullable (`SET_NULL`) purely so an entry survives its actor being deleted later
    (an employee removed after they took the logged action) — `user_name_snapshot` is what keeps
    the row readable once that happens, since `user.name` is no longer reachable through the FK.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='audit_log_entries')
    user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_log_entries',
    )
    user_name_snapshot = models.CharField(max_length=255)
    action = models.CharField(max_length=64, help_text='e.g. "batch.created", "protocol.updated", "farm.reset".')
    target_description = models.CharField(max_length=255, help_text='Human-readable, e.g. "Bande Printemps 2026".')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.action} · {self.target_description}'
