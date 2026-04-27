from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pricing_v4.models import ChargeAlias, ProductCode


@dataclass(frozen=True)
class AliasSeedRow:
    alias_text: str
    match_type: str
    mode_scope: str
    direction_scope: str
    product_code_code: str
    priority: int
    is_active: bool = True
    notes: str = ""


PACK_A_ALIASES: tuple[AliasSeedRow, ...] = (
    # Export - exact, direction-scoped starter aliases.
    AliasSeedRow("Air Freight", "EXACT", "EXPORT", "MAIN", "EXP-FRT-AIR", 10, notes="Pack A exact freight alias"),
    AliasSeedRow("Airfreight", "EXACT", "EXPORT", "MAIN", "EXP-FRT-AIR", 10, notes="Pack A exact freight alias"),
    AliasSeedRow("Documentation Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-DOC", 20, notes="Pack A exact documentation alias"),
    AliasSeedRow("Doc Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-DOC", 20, notes="Pack A exact documentation alias"),
    AliasSeedRow("AWB Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-AWB", 20, notes="Pack A exact documentation alias"),
    AliasSeedRow("Customs Clearance", "EXACT", "EXPORT", "ORIGIN", "EXP-CLEAR", 30, notes="Pack A exact clearance alias"),
    AliasSeedRow("Agency Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-AGENCY", 30, notes="Pack A exact agency alias"),
    AliasSeedRow("Terminal Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-TERM", 30, notes="Pack A exact terminal alias"),
    AliasSeedRow("Handling Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-HANDLE", 30, notes="Pack A exact handling alias"),
    AliasSeedRow("Build Up Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-BUILDUP", 30, notes="Pack A exact handling alias"),
    AliasSeedRow("Security Screening", "EXACT", "EXPORT", "ORIGIN", "EXP-SCREEN", 30, notes="Pack A exact screening alias"),
    AliasSeedRow("Pickup", "EXACT", "EXPORT", "ORIGIN", "EXP-PICKUP", 40, notes="Pack A exact pickup alias"),
    AliasSeedRow("Pickup Fee", "EXACT", "EXPORT", "ORIGIN", "EXP-PICKUP", 40, notes="Pack A exact pickup alias"),
    AliasSeedRow("Destination Clearance", "EXACT", "EXPORT", "DESTINATION", "EXP-CLEAR-DEST", 40, notes="Pack A exact destination alias"),
    AliasSeedRow("Destination Delivery", "EXACT", "EXPORT", "DESTINATION", "EXP-DELIVERY-DEST", 40, notes="Pack A exact destination alias"),

    # Import - exact aliases split by origin/destination direction.
    AliasSeedRow("Air Freight", "EXACT", "IMPORT", "MAIN", "IMP-FRT-AIR", 10, notes="Pack A exact freight alias"),
    AliasSeedRow("Airfreight", "EXACT", "IMPORT", "MAIN", "IMP-FRT-AIR", 10, notes="Pack A exact freight alias"),
    AliasSeedRow("Documentation Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-DOC-ORIGIN", 20, notes="Pack A exact origin documentation alias"),
    AliasSeedRow("Doc Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-DOC-ORIGIN", 20, notes="Pack A exact origin documentation alias"),
    AliasSeedRow("Export License", "EXACT", "IMPORT", "ORIGIN", "IMP-PRM-ORIGIN", 20, notes="Pack A China-agent origin permit/license alias"),
    AliasSeedRow("AWB Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-AWB-ORIGIN", 20, notes="Pack A exact origin documentation alias"),
    AliasSeedRow("Origin Agency Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-AGENCY-ORIGIN", 30, notes="Pack A exact origin agency alias"),
    AliasSeedRow("Import Agency Fee (Origin)", "EXACT", "IMPORT", "ORIGIN", "IMP-AGENCY-ORIGIN", 30, notes="Pack A exact origin agency display alias"),
    AliasSeedRow("CUS", "EXACT", "IMPORT", "ORIGIN", "IMP-CUS-CLR-ORIGIN", 30, notes="Pack A China-agent customs abbreviation alias"),
    AliasSeedRow("Customs Clearance", "EXACT", "IMPORT", "ORIGIN", "IMP-CUS-CLR-ORIGIN", 30, notes="Pack A China-agent origin customs alias"),
    AliasSeedRow("Import Origin Customs Clearance", "EXACT", "IMPORT", "ORIGIN", "IMP-CUS-CLR-ORIGIN", 30, notes="Pack A exact origin customs display alias"),
    AliasSeedRow("CTO Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-CTO-ORIGIN", 30, notes="Pack A exact origin terminal alias"),
    AliasSeedRow("HANDLE", "EXACT", "IMPORT", "ORIGIN", "IMP-CTO-ORIGIN", 30, notes="Pack A China-agent handling abbreviation alias"),
    AliasSeedRow("Handling Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-CTO-ORIGIN", 30, notes="Pack A China-agent origin handling alias"),
    AliasSeedRow("X-Ray Screening", "EXACT", "IMPORT", "ORIGIN", "IMP-SCREEN-ORIGIN", 30, notes="Pack A exact screening alias"),
    AliasSeedRow("Pickup", "EXACT", "IMPORT", "ORIGIN", "IMP-PICKUP", 40, notes="Pack A exact pickup alias"),
    AliasSeedRow("Pickup Fee", "EXACT", "IMPORT", "ORIGIN", "IMP-PICKUP", 40, notes="Pack A exact pickup alias"),
    AliasSeedRow("Pickup Charge", "EXACT", "IMPORT", "ORIGIN", "IMP-PICKUP", 40, notes="Pack A China-agent pickup alias"),
    AliasSeedRow("Pick Up+Gate In", "EXACT", "IMPORT", "ORIGIN", "IMP-PICKUP", 40, notes="Pack A China-agent pickup/gate-in alias"),
    AliasSeedRow("Pick Up + Gate In", "EXACT", "IMPORT", "ORIGIN", "IMP-PICKUP", 40, notes="Pack A China-agent pickup/gate-in alias"),
    AliasSeedRow("A/F", "EXACT", "IMPORT", "MAIN", "IMP-FRT-AIR", 10, notes="Pack A China-agent airfreight abbreviation alias"),
    AliasSeedRow("Customs Clearance", "EXACT", "IMPORT", "DESTINATION", "IMP-CLEAR", 30, notes="Pack A exact destination clearance alias"),
    AliasSeedRow("Agency Fee", "EXACT", "IMPORT", "DESTINATION", "IMP-AGENCY-DEST", 30, notes="Pack A exact destination agency alias"),
    AliasSeedRow("Documentation Fee", "EXACT", "IMPORT", "DESTINATION", "IMP-DOC-DEST", 30, notes="Pack A exact destination documentation alias"),
    AliasSeedRow("Handling Fee", "EXACT", "IMPORT", "DESTINATION", "IMP-HANDLING-DEST", 30, notes="Pack A exact destination handling alias"),
    AliasSeedRow("Loading Fee", "EXACT", "IMPORT", "DESTINATION", "IMP-LOADING-DEST", 30, notes="Pack A exact destination handling alias"),
    AliasSeedRow("Cartage", "EXACT", "IMPORT", "DESTINATION", "IMP-CARTAGE-DEST", 40, notes="Pack A exact destination cartage alias"),
    AliasSeedRow("Delivery", "EXACT", "IMPORT", "DESTINATION", "IMP-CARTAGE-DEST", 40, notes="Pack A exact destination cartage alias"),

    # Domestic - exact starter aliases only.
    AliasSeedRow("Air Freight", "EXACT", "DOMESTIC", "MAIN", "DOM-FRT-AIR", 10, notes="Pack A exact domestic freight alias"),
    AliasSeedRow("Airfreight", "EXACT", "DOMESTIC", "MAIN", "DOM-FRT-AIR", 10, notes="Pack A exact domestic freight alias"),
    AliasSeedRow("Documentation Fee", "EXACT", "DOMESTIC", "ORIGIN", "DOM-DOC", 20, notes="Pack A exact domestic documentation alias"),
    AliasSeedRow("Doc Fee", "EXACT", "DOMESTIC", "ORIGIN", "DOM-DOC", 20, notes="Pack A exact domestic documentation alias"),
    AliasSeedRow("Terminal Fee", "EXACT", "DOMESTIC", "ORIGIN", "DOM-TERMINAL", 30, notes="Pack A exact domestic terminal alias"),
    AliasSeedRow("AWB Fee", "EXACT", "DOMESTIC", "ORIGIN", "DOM-AWB", 30, notes="Pack A exact domestic AWB alias"),
    AliasSeedRow("Security Surcharge", "EXACT", "DOMESTIC", "ORIGIN", "DOM-SECURITY", 30, notes="Pack A exact domestic security alias"),
    AliasSeedRow("Fuel Surcharge", "EXACT", "DOMESTIC", "ORIGIN", "DOM-FSC", 30, notes="Pack A exact domestic fuel alias"),
)

# Pack B intentionally left unloaded. Add rows here later and wire them into
# ACTIVE_SEED_PACKS only after review because Pack B may include broader rules.
PACK_B_ALIASES: tuple[AliasSeedRow, ...] = ()
ACTIVE_SEED_PACKS: tuple[tuple[str, tuple[AliasSeedRow, ...]], ...] = (
    ("Pack A", PACK_A_ALIASES),
)


class Command(BaseCommand):
    help = "Safely seed baseline ChargeAlias records from embedded Pack A aliases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing ChargeAlias rows.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        rows = tuple(row for _, pack_rows in ACTIVE_SEED_PACKS for row in pack_rows)
        summary = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "missing": [],
            "warnings": [],
        }

        self.stdout.write("=" * 72)
        self.stdout.write("Seeding ChargeAlias records")
        self.stdout.write("=" * 72)
        self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
        self.stdout.write(f"Packs: {', '.join(name for name, _ in ACTIVE_SEED_PACKS)}")
        self.stdout.write(f"Rows:  {len(rows)}")
        self.stdout.write("")

        self._warn_dataset_duplicates(rows, summary)
        product_codes = self._load_product_codes(rows, summary)

        with transaction.atomic():
            for row_number, row in enumerate(rows, start=1):
                self._process_row(row_number, row, product_codes, dry_run, summary)

            if dry_run or summary["missing"]:
                transaction.set_rollback(True)

        self._print_summary(summary, dry_run)

        if summary["missing"]:
            missing_codes = ", ".join(sorted(set(summary["missing"])))
            raise CommandError(f"Missing ProductCode code(s): {missing_codes}")

    def _process_row(
        self,
        row_number: int,
        row: AliasSeedRow,
        product_codes: dict[str, ProductCode],
        dry_run: bool,
        summary: dict,
    ):
        product = product_codes.get(row.product_code_code)
        if product is None:
            summary["skipped"] += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  SKIP row {row_number}: missing ProductCode {row.product_code_code} for '{row.alias_text}'"
                )
            )
            return

        try:
            self._validate_row(row_number, row)
        except CommandError as exc:
            summary["skipped"] += 1
            summary["warnings"].append(str(exc))
            self.stdout.write(self.style.WARNING(f"  SKIP row {row_number}: {exc}"))
            return

        normalized_alias_text = ChargeAlias.normalize_alias_text_value(row.alias_text)
        lookup = {
            "normalized_alias_text": normalized_alias_text,
            "match_type": row.match_type,
            "mode_scope": row.mode_scope,
            "direction_scope": row.direction_scope,
            "product_code": product,
        }
        defaults = {
            "alias_text": row.alias_text.strip(),
            "priority": row.priority,
            "is_active": row.is_active,
            "alias_source": ChargeAlias.AliasSource.SEED,
            "review_status": ChargeAlias.ReviewStatus.APPROVED,
            "notes": row.notes,
        }

        same_target = ChargeAlias.objects.filter(**lookup).order_by("id")
        if same_target.count() > 1:
            summary["skipped"] += 1
            warning = (
                f"row {row_number}: duplicate existing aliases for '{row.alias_text}' "
                f"{row.match_type}/{row.mode_scope}/{row.direction_scope} -> {row.product_code_code}"
            )
            summary["warnings"].append(warning)
            self.stdout.write(self.style.WARNING(f"  SKIP {warning}"))
            return

        conflicts = ChargeAlias.objects.filter(
            normalized_alias_text=normalized_alias_text,
            match_type=row.match_type,
            mode_scope=row.mode_scope,
            direction_scope=row.direction_scope,
            is_active=True,
        ).exclude(product_code=product)
        if row.is_active and conflicts.exists():
            summary["skipped"] += 1
            warning = (
                f"row {row_number}: active conflict for '{row.alias_text}' "
                f"{row.match_type}/{row.mode_scope}/{row.direction_scope}; "
                f"existing ProductCodes={', '.join(conflicts.values_list('product_code__code', flat=True).distinct())}"
            )
            summary["warnings"].append(warning)
            self.stdout.write(self.style.WARNING(f"  SKIP {warning}"))
            return

        existing = same_target.first()
        if existing:
            changed = self._apply_defaults(existing, defaults)
            if not changed:
                summary["skipped"] += 1
                self.stdout.write(f"  Reused {row.alias_text} -> {row.product_code_code}")
                return

            existing.full_clean()
            summary["updated"] += 1
            action = "Would update" if dry_run else "Updated"
            if not dry_run:
                existing.save()
            self.stdout.write(f"  {action} {row.alias_text} -> {row.product_code_code}")
            return

        alias = ChargeAlias(**lookup, **defaults)
        alias.full_clean()
        summary["created"] += 1
        action = "Would create" if dry_run else "Created"
        if not dry_run:
            alias.save()
        self.stdout.write(f"  {action} {row.alias_text} -> {row.product_code_code}")

    def _load_product_codes(self, rows: Iterable[AliasSeedRow], summary: dict) -> dict[str, ProductCode]:
        codes = sorted({row.product_code_code for row in rows})
        product_codes = {
            product.code: product
            for product in ProductCode.objects.filter(code__in=codes)
        }
        missing = [code for code in codes if code not in product_codes]
        summary["missing"].extend(missing)
        return product_codes

    def _warn_dataset_duplicates(self, rows: Iterable[AliasSeedRow], summary: dict):
        seen: dict[tuple[str, str, str, str], AliasSeedRow] = {}
        for row in rows:
            key = (
                ChargeAlias.normalize_alias_text_value(row.alias_text),
                row.match_type,
                row.mode_scope,
                row.direction_scope,
            )
            previous = seen.get(key)
            if previous is None:
                seen[key] = row
                continue
            if previous.product_code_code == row.product_code_code:
                continue

            warning = (
                "dataset conflict: "
                f"'{row.alias_text}' {row.match_type}/{row.mode_scope}/{row.direction_scope} "
                f"targets both {previous.product_code_code} and {row.product_code_code}"
            )
            summary["warnings"].append(warning)
            self.stdout.write(self.style.WARNING(f"  WARNING {warning}"))

    def _validate_row(self, row_number: int, row: AliasSeedRow):
        if row.match_type not in ChargeAlias.MatchType.values:
            raise CommandError(f"row {row_number}: invalid match_type '{row.match_type}'")
        if row.mode_scope not in ChargeAlias.ModeScope.values:
            raise CommandError(f"row {row_number}: invalid mode_scope '{row.mode_scope}'")
        if row.direction_scope not in ChargeAlias.DirectionScope.values:
            raise CommandError(f"row {row_number}: invalid direction_scope '{row.direction_scope}'")
        if not row.alias_text.strip():
            raise CommandError(f"row {row_number}: alias_text cannot be blank")
        if row.priority < 1:
            raise CommandError(f"row {row_number}: priority must be positive")

    @staticmethod
    def _apply_defaults(alias: ChargeAlias, defaults: dict) -> bool:
        changed = False
        for field, value in defaults.items():
            if getattr(alias, field) != value:
                setattr(alias, field, value)
                changed = True
        return changed

    def _print_summary(self, summary: dict, dry_run: bool):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"[{'DRY RUN' if dry_run else 'APPLIED'}] ChargeAlias seed summary"))
        self.stdout.write(f"- Created: {summary['created']}")
        self.stdout.write(f"- Updated: {summary['updated']}")
        self.stdout.write(f"- Skipped: {summary['skipped']}")
        self.stdout.write(f"- Missing ProductCodes: {len(summary['missing'])}")
        for code in sorted(set(summary["missing"])):
            self.stdout.write(self.style.ERROR(f"  - {code}"))
        self.stdout.write(f"- Duplicate/conflict warnings: {len(summary['warnings'])}")
        for warning in summary["warnings"]:
            self.stdout.write(self.style.WARNING(f"  - {warning}"))
