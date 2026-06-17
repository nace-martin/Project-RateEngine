import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.models import CustomUser
from accounts.scope import get_active_memberships
from quotes.rbac_selector_comparison import (
    compare_quote_visibility,
    compare_spe_visibility,
)


class Command(BaseCommand):
    help = (
        "Read-only diagnostic comparing legacy quote/SPE selector visibility "
        "with UserMembership-derived visibility."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )
        parser.add_argument(
            "--user",
            dest="user_lookup",
            help="Limit comparison to one user by username or numeric ID.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive users. Inactive users are skipped by default.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Limit the number of users compared.",
        )
        parser.add_argument(
            "--show-details",
            action="store_true",
            help="Include record ID lists in output.",
        )

    def handle(self, *args, **options):
        users = self._get_users(options)
        rows = [self._build_user_row(user, show_details=options["show_details"]) for user in users]

        payload = {
            "summary": self._build_summary(rows),
            "users": rows,
        }

        if options["format"] == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self._write_text(payload, show_details=options["show_details"])

    def _get_users(self, options):
        queryset = CustomUser.objects.all().order_by("username", "id")

        if not options["include_inactive"]:
            queryset = queryset.filter(is_active=True)

        user_lookup = options.get("user_lookup")
        if user_lookup:
            lookup = Q(username=user_lookup)
            if user_lookup.isdigit():
                lookup |= Q(pk=int(user_lookup))
            queryset = queryset.filter(lookup)

        limit = options.get("limit")
        if limit is not None:
            if limit < 1:
                raise CommandError("--limit must be a positive integer.")
            queryset = queryset[:limit]

        users = list(queryset)
        if user_lookup and not users:
            raise CommandError(f"No user found for --user={user_lookup!r}.")
        return users

    def _build_user_row(self, user, *, show_details: bool) -> dict:
        memberships = list(get_active_memberships(user))
        quote_comparison = compare_quote_visibility(user)
        spe_comparison = compare_spe_visibility(user)

        return {
            "user_id": user.pk,
            "username": user.username,
            "is_active": user.is_active,
            "role": getattr(user, "role", ""),
            "legacy_department": getattr(user, "department", None),
            "membership_count": len(memberships),
            "quotes": quote_comparison.as_dict(show_details=show_details),
            "spes": spe_comparison.as_dict(show_details=show_details),
            "has_mismatch": quote_comparison.has_mismatch or spe_comparison.has_mismatch,
        }

    def _build_summary(self, rows: list[dict]) -> dict:
        return {
            "users_compared": len(rows),
            "users_with_mismatches": sum(1 for row in rows if row["has_mismatch"]),
            "quote_legacy_only_count": sum(row["quotes"]["legacy_only_count"] for row in rows),
            "quote_membership_only_count": sum(row["quotes"]["membership_only_count"] for row in rows),
            "spe_legacy_only_count": sum(row["spes"]["legacy_only_count"] for row in rows),
            "spe_membership_only_count": sum(row["spes"]["membership_only_count"] for row in rows),
        }

    def _write_text(self, payload: dict, *, show_details: bool):
        summary = payload["summary"]
        self.stdout.write("RBAC visibility comparison")
        self.stdout.write("==========================")
        self.stdout.write(f"Users compared: {summary['users_compared']}")
        self.stdout.write(f"Users with mismatches: {summary['users_with_mismatches']}")
        self.stdout.write(
            "Quote mismatches: "
            f"legacy-only={summary['quote_legacy_only_count']}, "
            f"membership-only={summary['quote_membership_only_count']}"
        )
        self.stdout.write(
            "SPE mismatches: "
            f"legacy-only={summary['spe_legacy_only_count']}, "
            f"membership-only={summary['spe_membership_only_count']}"
        )

        for row in payload["users"]:
            self.stdout.write("")
            self.stdout.write(
                f"- {row['username']} (id={row['user_id']}, active={row['is_active']}, "
                f"role={row['role']}, legacy_department={row['legacy_department']}, "
                f"memberships={row['membership_count']})"
            )
            self.stdout.write(
                self._format_counts("quotes", row["quotes"])
            )
            self.stdout.write(
                self._format_counts("SPEs", row["spes"])
            )
            if show_details:
                self._write_details("quotes", row["quotes"])
                self._write_details("SPEs", row["spes"])

    def _format_counts(self, label: str, counts: dict) -> str:
        return (
            f"  {label}: legacy={counts['legacy_count']}, "
            f"membership={counts['membership_count']}, "
            f"matching={counts['matching_count']}, "
            f"legacy-only={counts['legacy_only_count']}, "
            f"membership-only={counts['membership_only_count']}, "
            f"mismatch={counts['has_mismatch']}"
        )

    def _write_details(self, label: str, counts: dict):
        self.stdout.write(f"  {label} legacy-only IDs: {counts['legacy_only_ids']}")
        self.stdout.write(f"  {label} membership-only IDs: {counts['membership_only_ids']}")
