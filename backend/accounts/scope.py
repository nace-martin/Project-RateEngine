from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import CustomUser, UserMembership


ORG_WIDE_ROLE_CODES = {
    CustomUser.ROLE_ADMIN,
    CustomUser.ROLE_FINANCE,
}

ORG_WIDE_PERMISSION_CODES = {
    "quote.view.organization",
    "report.view.financials",
    "user.manage",
    "system.settings",
}

LEGACY_PERMISSION_CHECKS = {
    "quote.view.buy_cost": "can_view_buy_charges",
    "rate.view.buy": "can_view_buy_charges",
    "quote.view.margin": "can_view_margins",
    "report.view.financials": "can_view_margins",
    "quote.create": "can_edit_quotes",
    "quote.edit": "can_edit_quotes",
    "quote.clone": "can_edit_quotes",
    "quote.transition": "can_edit_quotes",
    "quote.export_pdf": "can_edit_quotes",
    "quote.finalize": "can_finalize_quotes",
    "spot.create": "can_use_ai_intake",
    "spot.analyze": "can_use_ai_intake",
    "spot.compute": "can_use_ai_intake",
    "spot.create_quote": "can_use_ai_intake",
    "spot.acknowledge": "can_use_ai_intake",
    "rate.edit": "can_edit_rate_cards",
    "fx.edit": "can_edit_fx_rates",
    "user.manage": "can_manage_users",
    "system.settings": "can_access_system_settings",
    "audit.view": "can_view_audit_logs",
}

LEGACY_AUTHENTICATED_PERMISSION_CODES = {
    "quote.view.own",
    "quote.view.sell",
    "customer.view",
    "crm.view",
    "shipment.view",
    "report.view.own",
}


@dataclass(frozen=True)
class EffectiveUserScope:
    organization_ids: frozenset[Any]
    branch_ids: frozenset[Any]
    department_ids: frozenset[Any]
    department_codes: frozenset[str]
    role_codes: frozenset[str]
    permission_codes: frozenset[str]
    has_active_memberships: bool
    has_null_branch_scope: bool
    has_null_department_scope: bool


@dataclass(frozen=True)
class CreateScope:
    organization: Any = None
    branch: Any = None
    department: Any = None
    owner: Any = None
    source: str = "none"
    reason: str = "No authenticated active user."


def _is_authenticated_active(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def _normalize_code(value) -> str:
    return str(value or "").strip().lower()


def _normalize_department_code(value) -> str:
    return str(value or "").strip().upper()


def get_active_memberships(user):
    if not _is_authenticated_active(user):
        return UserMembership.objects.none()

    return (
        UserMembership.objects.filter(user=user, is_active=True)
        .select_related("organization", "branch", "department", "role")
        .prefetch_related("role__permissions")
    )


def _agreed_membership_value(memberships, field_name, id_field_name):
    values = {getattr(membership, id_field_name, None) for membership in memberships}
    if len(values) == 1 and next(iter(values)) is not None:
        return getattr(memberships[0], field_name)
    return None


def resolve_create_scope_for_user(user) -> CreateScope:
    if not _is_authenticated_active(user):
        return CreateScope()

    memberships = list(get_active_memberships(user))
    if len(memberships) == 1:
        membership = memberships[0]
        return CreateScope(
            organization=membership.organization,
            branch=membership.branch,
            department=membership.department,
            owner=user,
            source="user_membership",
            reason="Exactly one active membership.",
        )

    if len(memberships) > 1:
        return CreateScope(
            organization=_agreed_membership_value(memberships, "organization", "organization_id"),
            branch=_agreed_membership_value(memberships, "branch", "branch_id"),
            department=_agreed_membership_value(memberships, "department", "department_id"),
            owner=user,
            source="user_memberships",
            reason="Multiple active memberships; only agreed scope values resolved.",
        )

    return CreateScope(
        organization=getattr(user, "organization", None),
        owner=user,
        source="legacy_user_fields",
        reason="No active memberships; using legacy user organization only.",
    )


def _membership_role_codes(membership) -> set[str]:
    role = getattr(membership, "role", None)
    if not role:
        return set()
    return {
        code
        for code in {
            _normalize_code(getattr(role, "code", "")),
            _normalize_code(getattr(role, "name", "")),
        }
        if code
    }


def _membership_permission_codes(membership) -> set[str]:
    role = getattr(membership, "role", None)
    if not role or not getattr(role, "is_active", True):
        return set()
    return {
        permission.code
        for permission in role.permissions.all()
        if getattr(permission, "is_active", True)
    }


def _membership_is_org_wide(membership) -> bool:
    role_codes = _membership_role_codes(membership)
    permission_codes = _membership_permission_codes(membership)
    return bool(
        role_codes.intersection(ORG_WIDE_ROLE_CODES)
        or permission_codes.intersection(ORG_WIDE_PERMISSION_CODES)
    )


def _legacy_permission_codes(user) -> set[str]:
    permission_codes = set()

    for permission_code in LEGACY_AUTHENTICATED_PERMISSION_CODES:
        permission_codes.add(permission_code)

    for permission_code, helper_name in LEGACY_PERMISSION_CHECKS.items():
        if bool(getattr(user, helper_name, False)):
            permission_codes.add(permission_code)

    return permission_codes


def get_effective_user_scope(user) -> EffectiveUserScope:
    if not _is_authenticated_active(user):
        return EffectiveUserScope(
            organization_ids=frozenset(),
            branch_ids=frozenset(),
            department_ids=frozenset(),
            department_codes=frozenset(),
            role_codes=frozenset(),
            permission_codes=frozenset(),
            has_active_memberships=False,
            has_null_branch_scope=False,
            has_null_department_scope=False,
        )

    memberships = list(get_active_memberships(user))
    if memberships:
        organization_ids = {
            membership.organization_id
            for membership in memberships
            if membership.organization_id
        }
        branch_ids = {
            membership.branch_id
            for membership in memberships
            if membership.branch_id
        }
        department_ids = {
            membership.department_id
            for membership in memberships
            if membership.department_id
        }
        department_codes = {
            _normalize_department_code(getattr(membership.department, "code", ""))
            for membership in memberships
            if membership.department_id
        }
        role_codes = set()
        permission_codes = set()
        has_null_branch_scope = False
        has_null_department_scope = False

        for membership in memberships:
            role_codes.update(_membership_role_codes(membership))
            permission_codes.update(_membership_permission_codes(membership))
            if _membership_is_org_wide(membership):
                has_null_branch_scope = has_null_branch_scope or membership.branch_id is None
                has_null_department_scope = (
                    has_null_department_scope or membership.department_id is None
                )

        return EffectiveUserScope(
            organization_ids=frozenset(organization_ids),
            branch_ids=frozenset(branch_ids),
            department_ids=frozenset(department_ids),
            department_codes=frozenset(department_codes),
            role_codes=frozenset(role_codes),
            permission_codes=frozenset(permission_codes),
            has_active_memberships=True,
            has_null_branch_scope=has_null_branch_scope,
            has_null_department_scope=has_null_department_scope,
        )

    role_code = _normalize_code(getattr(user, "role", ""))
    department_code = _normalize_department_code(getattr(user, "department", ""))
    organization_id = getattr(user, "organization_id", None)

    return EffectiveUserScope(
        organization_ids=frozenset({organization_id} if organization_id else set()),
        branch_ids=frozenset(),
        department_ids=frozenset(),
        department_codes=frozenset({department_code} if department_code else set()),
        role_codes=frozenset({role_code} if role_code else set()),
        permission_codes=frozenset(_legacy_permission_codes(user)),
        has_active_memberships=False,
        has_null_branch_scope=role_code in ORG_WIDE_ROLE_CODES and bool(organization_id),
        has_null_department_scope=role_code in ORG_WIDE_ROLE_CODES and bool(organization_id),
    )


def user_has_permission(user, permission_code) -> bool:
    if not _is_authenticated_active(user):
        return False

    normalized_permission_code = str(permission_code or "").strip()
    if not normalized_permission_code:
        return False

    memberships = list(get_active_memberships(user))
    if memberships:
        return any(
            normalized_permission_code in _membership_permission_codes(membership)
            for membership in memberships
        )

    if normalized_permission_code in LEGACY_AUTHENTICATED_PERMISSION_CODES:
        return True

    helper_name = LEGACY_PERMISSION_CHECKS.get(normalized_permission_code)
    return bool(helper_name and getattr(user, helper_name, False))


def user_has_role(user, role_code_or_name) -> bool:
    if not _is_authenticated_active(user):
        return False

    normalized_role = _normalize_code(role_code_or_name)
    if not normalized_role:
        return False

    return normalized_role in get_effective_user_scope(user).role_codes


def user_can_access_organization(user, organization) -> bool:
    if not _is_authenticated_active(user) or not organization:
        return False

    if getattr(user, "is_superuser", False):
        return True

    organization_id = getattr(organization, "id", organization)
    return organization_id in get_effective_user_scope(user).organization_ids


def user_can_access_branch(user, branch) -> bool:
    if not _is_authenticated_active(user) or not branch:
        return False

    if getattr(user, "is_superuser", False):
        return True

    scope = get_effective_user_scope(user)
    branch_id = getattr(branch, "id", branch)
    if branch_id in scope.branch_ids:
        return True

    branch_organization_id = getattr(branch, "organization_id", None)
    if branch_organization_id not in scope.organization_ids:
        return False

    if not scope.has_null_branch_scope:
        return False

    if scope.has_active_memberships:
        return any(
            membership.organization_id == branch_organization_id
            and membership.branch_id is None
            and _membership_is_org_wide(membership)
            for membership in get_active_memberships(user)
        )

    return bool(scope.role_codes.intersection(ORG_WIDE_ROLE_CODES))


def user_can_access_department(user, department) -> bool:
    if not _is_authenticated_active(user) or not department:
        return False

    if getattr(user, "is_superuser", False):
        return True

    scope = get_effective_user_scope(user)
    department_id = getattr(department, "id", department)
    if department_id in scope.department_ids:
        return True

    department_organization_id = getattr(department, "organization_id", None)
    if department_organization_id not in scope.organization_ids:
        return False

    department_code = _normalize_department_code(getattr(department, "code", ""))
    if not scope.has_active_memberships and department_code in scope.department_codes:
        return True

    if not scope.has_null_department_scope:
        return False

    if scope.has_active_memberships:
        return any(
            membership.organization_id == department_organization_id
            and membership.department_id is None
            and _membership_is_org_wide(membership)
            for membership in get_active_memberships(user)
        )

    return bool(scope.role_codes.intersection(ORG_WIDE_ROLE_CODES))
