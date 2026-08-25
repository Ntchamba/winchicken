from rest_framework.permissions import BasePermission

from apps.core.models import UserRole

ADMIN = UserRole.ADMIN
SECONDARY_ADMIN = UserRole.SECONDARY_ADMIN
FARM_MANAGER = UserRole.FARM_MANAGER
FARMER = UserRole.FARMER
WORKER = UserRole.WORKER
TECHNICIAN = UserRole.TECHNICIAN
CASHIER = UserRole.CASHIER


def role_permission(*allowed_roles):
    """Builds a DRF permission class allowing only the given roles (section 8 permission matrix)."""

    class _RolePermission(BasePermission):
        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and user.role in allowed_roles)

    return _RolePermission


IsAdmin = role_permission(ADMIN)
IsAdminOrFarmManager = role_permission(ADMIN, FARM_MANAGER)
IsAdminOrSecondaryAdmin = role_permission(ADMIN, SECONDARY_ADMIN)
IsAdminOrCashier = role_permission(ADMIN, CASHIER)
IsAdminOrTechnician = role_permission(ADMIN, TECHNICIAN)
IsAdminOrFarmManagerOrFarmer = role_permission(ADMIN, FARM_MANAGER, FARMER)
IsFarmerOrWorker = role_permission(FARMER, WORKER)
CanEditHouseProtocol = role_permission(ADMIN, FARM_MANAGER, FARMER)
