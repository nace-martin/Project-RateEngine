from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from accounts.models import CustomUser, Permission, Role, RolePermission, UserMembership
from parties.models import Branch, Department, Organization


DEFAULT_EFM_ORGANIZATION_SLUGS = {"efm", "efm-express-air-cargo"}

DEFAULT_BRANCHES = [
    {"code": "POM", "name": "Port Moresby"},
    {"code": "LAE", "name": "Lae"},
    {"code": "BNE", "name": "Brisbane"},
    {"code": "FIJ", "name": "Fiji"},
    {"code": "SOL", "name": "Solomon Islands"},
]

DEFAULT_DEPARTMENTS = [
    {"code": "AIR", "name": "Air Freight"},
    {"code": "SEA", "name": "Sea Freight"},
    {"code": "LAND", "name": "Land Freight"},
    {"code": "FINANCE", "name": "Finance"},
    {"code": "ADMIN", "name": "Administration"},
]

DEFAULT_PERMISSIONS = [
    ("quote.view.own", "View own quotes"),
    ("quote.view.department", "View department quotes"),
    ("quote.view.organization", "View organization quotes"),
    ("quote.create", "Create quotes"),
    ("quote.edit", "Edit quotes"),
    ("quote.finalize", "Finalize quotes"),
    ("quote.transition", "Transition quote status"),
    ("quote.clone", "Clone quotes"),
    ("quote.export_pdf", "Export quote PDF"),
    ("quote.view.sell", "View sell charges"),
    ("quote.view.buy_cost", "View buy cost charges"),
    ("quote.view.margin", "View margin"),
    ("spot.create", "Create SPOT envelopes"),
    ("spot.analyze", "Analyze SPOT replies"),
    ("spot.review", "Review SPOT charge exceptions"),
    ("spot.acknowledge", "Acknowledge SPOT envelopes"),
    ("spot.compute", "Compute SPOT quotes"),
    ("spot.create_quote", "Create quotes from SPOT envelopes"),
    ("customer.view", "View customers"),
    ("customer.manage", "Manage customers"),
    ("crm.view", "View CRM records"),
    ("crm.manage", "Manage CRM records"),
    ("shipment.view", "View shipments"),
    ("shipment.manage", "Manage shipments"),
    ("rate.view.sell", "View sell rates"),
    ("rate.view.buy", "View buy rates"),
    ("rate.edit", "Edit rates"),
    ("fx.edit", "Edit FX rates"),
    ("report.view.own", "View own reports"),
    ("report.view.financials", "View financial reports"),
    ("user.manage", "Manage users"),
    ("system.settings", "Access system settings"),
]

ROLE_DEFINITIONS = {
    CustomUser.ROLE_SALES: {
        "name": "Sales",
        "permissions": {
            "quote.view.own",
            "quote.create",
            "quote.edit",
            "quote.finalize",
            "quote.transition",
            "quote.clone",
            "quote.export_pdf",
            "quote.view.sell",
            "quote.view.buy_cost",
            "spot.create",
            "spot.analyze",
            "spot.acknowledge",
            "spot.compute",
            "spot.create_quote",
            "customer.view",
            "crm.view",
            "crm.manage",
            "shipment.view",
            "shipment.manage",
            "report.view.own",
        },
    },
    CustomUser.ROLE_MANAGER: {
        "name": "Manager",
        "permissions": {
            "quote.view.own",
            "quote.view.department",
            "quote.create",
            "quote.edit",
            "quote.finalize",
            "quote.transition",
            "quote.clone",
            "quote.export_pdf",
            "quote.view.sell",
            "quote.view.buy_cost",
            "quote.view.margin",
            "spot.create",
            "spot.analyze",
            "spot.review",
            "spot.acknowledge",
            "spot.compute",
            "spot.create_quote",
            "customer.view",
            "crm.view",
            "crm.manage",
            "shipment.view",
            "shipment.manage",
            "rate.view.sell",
            "rate.view.buy",
            "rate.edit",
            "report.view.own",
            "report.view.financials",
            "user.manage",
        },
    },
    CustomUser.ROLE_FINANCE: {
        "name": "Finance",
        "permissions": {
            "quote.view.own",
            "quote.view.organization",
            "quote.export_pdf",
            "quote.view.sell",
            "quote.view.buy_cost",
            "quote.view.margin",
            "customer.view",
            "crm.view",
            "shipment.view",
            "rate.view.sell",
            "rate.view.buy",
            "fx.edit",
            "report.view.own",
            "report.view.financials",
            "user.manage",
        },
    },
    CustomUser.ROLE_ADMIN: {
        "name": "Admin",
        "permissions": {code for code, _name in DEFAULT_PERMISSIONS},
    },
}


@dataclass
class SeedSummary:
    branches_created: int = 0
    branches_existing: int = 0
    departments_created: int = 0
    departments_existing: int = 0
    permissions_created: int = 0
    permissions_existing: int = 0
    roles_created: int = 0
    roles_existing: int = 0
    role_permissions_created: int = 0
    role_permissions_existing: int = 0
    memberships_created: int = 0
    memberships_updated: int = 0
    memberships_existing: int = 0
    skipped_null_organization: list[str] = field(default_factory=list)
    skipped_unknown_role: list[str] = field(default_factory=list)
    skipped_unknown_department: list[str] = field(default_factory=list)
    users_missing_department: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "branches": {"created": self.branches_created, "existing": self.branches_existing},
            "departments": {"created": self.departments_created, "existing": self.departments_existing},
            "permissions": {"created": self.permissions_created, "existing": self.permissions_existing},
            "roles": {"created": self.roles_created, "existing": self.roles_existing},
            "role_permissions": {
                "created": self.role_permissions_created,
                "existing": self.role_permissions_existing,
            },
            "memberships": {
                "created": self.memberships_created,
                "updated": self.memberships_updated,
                "existing": self.memberships_existing,
            },
            "skipped": {
                "null_organization": self.skipped_null_organization,
                "unknown_role": self.skipped_unknown_role,
                "unknown_department": self.skipped_unknown_department,
            },
            "reported": {
                "users_missing_department": self.users_missing_department,
            },
        }


def _seed_branches(summary: SeedSummary):
    organizations = Organization.objects.filter(slug__in=DEFAULT_EFM_ORGANIZATION_SLUGS).order_by("slug")
    for organization in organizations:
        for item in DEFAULT_BRANCHES:
            _branch, created = Branch.objects.get_or_create(
                organization=organization,
                code=item["code"],
                defaults={"name": item["name"], "is_active": True},
            )
            if created:
                summary.branches_created += 1
            else:
                summary.branches_existing += 1


def _seed_departments(summary: SeedSummary):
    organizations = Organization.objects.order_by("slug")
    for organization in organizations:
        for item in DEFAULT_DEPARTMENTS:
            _department, created = Department.objects.get_or_create(
                organization=organization,
                code=item["code"],
                defaults={"name": item["name"], "is_active": True},
            )
            if created:
                summary.departments_created += 1
            else:
                summary.departments_existing += 1


def _seed_permissions(summary: SeedSummary):
    for code, name in DEFAULT_PERMISSIONS:
        _permission, created = Permission.objects.get_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        if created:
            summary.permissions_created += 1
        else:
            summary.permissions_existing += 1


def _seed_roles(summary: SeedSummary) -> dict[str, Role]:
    roles = {}
    permissions_by_code = {permission.code: permission for permission in Permission.objects.all()}
    for code, definition in ROLE_DEFINITIONS.items():
        role, created = Role.objects.get_or_create(
            organization=None,
            code=code,
            defaults={
                "name": definition["name"],
                "description": f"System template for current {definition['name']} behavior.",
                "is_system": True,
                "is_active": True,
            },
        )
        roles[code] = role
        if created:
            summary.roles_created += 1
        else:
            summary.roles_existing += 1

        desired_permissions = definition["permissions"]
        RolePermission.objects.filter(role=role).exclude(permission__code__in=desired_permissions).delete()
        for permission_code in sorted(desired_permissions):
            permission = permissions_by_code[permission_code]
            _role_permission, rp_created = RolePermission.objects.get_or_create(
                role=role,
                permission=permission,
            )
            if rp_created:
                summary.role_permissions_created += 1
            else:
                summary.role_permissions_existing += 1
    return roles


def _seed_memberships(summary: SeedSummary, roles: dict[str, Role]):
    users = CustomUser.objects.select_related("organization").order_by("username")
    for user in users:
        if not user.organization_id:
            summary.skipped_null_organization.append(user.username)
            continue

        role = roles.get(user.role)
        if role is None:
            summary.skipped_unknown_role.append(user.username)
            continue

        department = None
        if user.department:
            department = Department.objects.filter(
                organization=user.organization,
                code=user.department,
            ).first()
            if department is None:
                summary.skipped_unknown_department.append(user.username)
                continue
        else:
            summary.users_missing_department.append(user.username)

        membership = UserMembership.objects.filter(
            user=user,
            is_primary=True,
            is_active=True,
        ).first()
        desired_values = {
            "organization": user.organization,
            "branch": None,
            "department": department,
            "role": role,
        }
        if membership is None:
            UserMembership.objects.create(
                user=user,
                is_primary=True,
                is_active=True,
                **desired_values,
            )
            summary.memberships_created += 1
            continue

        needs_update = any(getattr(membership, field_name) != value for field_name, value in desired_values.items())
        if needs_update:
            for field_name, value in desired_values.items():
                setattr(membership, field_name, value)
            membership.save(update_fields=["organization", "branch", "department", "role", "updated_at"])
            summary.memberships_updated += 1
        else:
            summary.memberships_existing += 1


@transaction.atomic
def seed_rbac_foundation() -> SeedSummary:
    summary = SeedSummary()
    _seed_branches(summary)
    _seed_departments(summary)
    _seed_permissions(summary)
    roles = _seed_roles(summary)
    _seed_memberships(summary, roles)
    return summary
