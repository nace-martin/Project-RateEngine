from __future__ import annotations

from decimal import Decimal

from pricing_v4.contracts.charge_context import (
    JourneyDirection,
    JourneyPattern,
    LegRole,
    ProductCodeDomain,
    TransportMode,
)
from quotes.contracts.journey_contracts import (
    PHASE_16E_A_RULE_VERSION,
    PNG_COUNTRY_CODE,
    PNG_GATEWAY_CODE,
    SUPPORTED_CUSTOMER_CODES,
    JourneyLeg,
    JourneyPlan,
    JourneyPlannerBlockerCode,
    JourneyRequest,
    JourneyStatus,
    coerce_journey_request,
)


class AirJourneyPlanner:
    """Pure deterministic Phase 16E-A air journey planner.

    It consumes only trusted server-side route/service inputs. It does not query
    rates, ProductCodes, aliases, AI, quotes or SPOT charge lines, and it does
    not mutate persistence.
    """

    rule_version = PHASE_16E_A_RULE_VERSION

    def plan(self, request: JourneyRequest | dict) -> JourneyPlan:
        normalized = coerce_journey_request(request)
        blockers: list[JourneyPlannerBlockerCode] = []
        self._request_validation_blockers(normalized, blockers)
        self._multi_stop_blockers(normalized, blockers)
        direction = self._direction(normalized, blockers)
        self._route_code_blockers(normalized, direction, blockers)
        pattern = self._pattern(normalized, direction, blockers)
        legs: list[JourneyLeg] = []
        if direction and pattern and not blockers:
            legs = self._legs(normalized, pattern)
            blockers.extend(self._validate_gateway(pattern, legs))
            blockers.extend(self._automation_blockers(pattern))

        return JourneyPlan(
            request=normalized,
            direction=direction,
            pattern=pattern,
            gateway_code=PNG_GATEWAY_CODE,
            route_policy_key=pattern.value if pattern else "UNSUPPORTED",
            rule_version=self.rule_version,
            input_fingerprint=normalized.input_fingerprint(),
            status=JourneyStatus.NEEDS_REVIEW if blockers else JourneyStatus.PLANNED,
            legs=legs,
            blockers=self._dedupe(blockers),
        )

    def _request_validation_blockers(self, request: JourneyRequest, blockers: list[JourneyPlannerBlockerCode]) -> None:
        for code in request.raw_evidence.get("_validation_blockers", []):
            blockers.append(JourneyPlannerBlockerCode(code))
        if not request.service_domain or request.service_domain != "AIR":
            blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID)
        if request.quote_date.isoformat() == "1970-01-01":
            blockers.append(JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID)

    def _multi_stop_blockers(self, request: JourneyRequest, blockers: list[JourneyPlannerBlockerCode]) -> None:
        for key in ["via", "via_code", "via_codes", "intermediate_code", "intermediate_codes", "stops"]:
            value = request.raw_evidence.get(key)
            if value:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_MULTI_STOP_UNSUPPORTED)
                return

    def _direction(
        self,
        request: JourneyRequest,
        blockers: list[JourneyPlannerBlockerCode],
    ) -> JourneyDirection | None:
        if not request.origin_country or not request.destination_country:
            blockers.append(JourneyPlannerBlockerCode.JOURNEY_COUNTRY_MISSING)
            return None
        if request.origin_country != PNG_COUNTRY_CODE and request.destination_country == PNG_COUNTRY_CODE:
            return JourneyDirection.IMPORT
        if request.origin_country == PNG_COUNTRY_CODE and request.destination_country != PNG_COUNTRY_CODE:
            return JourneyDirection.EXPORT
        blockers.append(JourneyPlannerBlockerCode.JOURNEY_DIRECTION_UNSUPPORTED)
        return None

    def _route_code_blockers(
        self,
        request: JourneyRequest,
        direction: JourneyDirection | None,
        blockers: list[JourneyPlannerBlockerCode],
    ) -> None:
        if direction == JourneyDirection.IMPORT:
            if not request.customer_origin_code:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)
            if request.origin_country != PNG_COUNTRY_CODE and request.customer_origin_code in SUPPORTED_CUSTOMER_CODES:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID)
            if request.destination_country == PNG_COUNTRY_CODE and request.customer_destination_code not in SUPPORTED_CUSTOMER_CODES:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)
        if direction == JourneyDirection.EXPORT:
            if not request.customer_destination_code:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)
            if request.destination_country != PNG_COUNTRY_CODE and request.customer_destination_code in SUPPORTED_CUSTOMER_CODES:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID)
            if request.origin_country == PNG_COUNTRY_CODE and request.customer_origin_code not in SUPPORTED_CUSTOMER_CODES:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)

    def _pattern(
        self,
        request: JourneyRequest,
        direction: JourneyDirection | None,
        blockers: list[JourneyPlannerBlockerCode],
    ) -> JourneyPattern | None:
        if direction is None:
            return None
        if direction == JourneyDirection.IMPORT:
            if request.customer_destination_code == "POM":
                return JourneyPattern.IMP_POM
            if request.customer_destination_code == "LAE":
                return JourneyPattern.IMP_LAE
            if request.customer_destination_code == "HGU":
                return JourneyPattern.IMP_HGU
            blockers.append(JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)
            return None
        if request.customer_origin_code == "POM":
            return JourneyPattern.EXP_POM
        if request.customer_origin_code == "LAE":
            return JourneyPattern.EXP_LAE
        if request.customer_origin_code == "HGU":
            return JourneyPattern.EXP_HGU
        blockers.append(JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)
        return None

    def _legs(self, request: JourneyRequest, pattern: JourneyPattern) -> list[JourneyLeg]:
        overseas_origin = request.customer_origin_code
        overseas_destination = request.customer_destination_code
        weight = request.chargeable_weight
        scope = request.service_scope
        if pattern == JourneyPattern.IMP_POM:
            return [self._leg(1, LegRole.INTERNATIONAL_IMPORT, TransportMode.INTERNATIONAL_AIR, overseas_origin, "POM", ProductCodeDomain.IMPORT, scope, weight)]
        if pattern == JourneyPattern.IMP_LAE:
            return [
                self._leg(1, LegRole.INTERNATIONAL_IMPORT, TransportMode.INTERNATIONAL_AIR, overseas_origin, "POM", ProductCodeDomain.IMPORT, scope, weight),
                self._leg(2, LegRole.DOMESTIC_ON_FORWARDING, TransportMode.DOMESTIC_AIR, "POM", "LAE", ProductCodeDomain.DOMESTIC, scope, weight),
            ]
        if pattern == JourneyPattern.IMP_HGU:
            return [
                self._leg(1, LegRole.INTERNATIONAL_IMPORT, TransportMode.INTERNATIONAL_AIR, overseas_origin, "POM", ProductCodeDomain.IMPORT, scope, weight),
                self._leg(2, LegRole.DOMESTIC_ON_FORWARDING, TransportMode.DOMESTIC_AIR, "POM", "HGU", ProductCodeDomain.DOMESTIC, scope, weight),
            ]
        if pattern == JourneyPattern.EXP_POM:
            return [self._leg(1, LegRole.INTERNATIONAL_EXPORT, TransportMode.INTERNATIONAL_AIR, "POM", overseas_destination, ProductCodeDomain.EXPORT, scope, weight)]
        if pattern == JourneyPattern.EXP_LAE:
            return [
                self._leg(1, LegRole.DOMESTIC_PRE_CARRIAGE, TransportMode.DOMESTIC_AIR, "LAE", "POM", ProductCodeDomain.DOMESTIC, scope, weight),
                self._leg(2, LegRole.INTERNATIONAL_EXPORT, TransportMode.INTERNATIONAL_AIR, "POM", overseas_destination, ProductCodeDomain.EXPORT, scope, weight),
            ]
        if pattern == JourneyPattern.EXP_HGU:
            return [
                self._leg(1, LegRole.DOMESTIC_PRE_CARRIAGE, TransportMode.DOMESTIC_AIR, "HGU", "POM", ProductCodeDomain.DOMESTIC, scope, weight),
                self._leg(2, LegRole.INTERNATIONAL_EXPORT, TransportMode.INTERNATIONAL_AIR, "POM", overseas_destination, ProductCodeDomain.EXPORT, scope, weight),
            ]
        return []

    def _leg(
        self,
        sequence: int,
        role: LegRole,
        mode: TransportMode,
        origin: str,
        destination: str,
        domain: ProductCodeDomain,
        service_scope: str,
        weight: Decimal | None,
    ) -> JourneyLeg:
        leg_key = f"{sequence:02d}:{role.value}:{origin}:{destination}"
        return JourneyLeg(
            sequence=sequence,
            leg_key=leg_key,
            role=role,
            transport_mode=mode,
            origin_code=origin,
            destination_code=destination,
            product_code_domain=domain,
            service_scope=service_scope,
            chargeable_weight=weight,
        )

    def _validate_gateway(self, pattern: JourneyPattern, legs: list[JourneyLeg]) -> list[JourneyPlannerBlockerCode]:
        blockers: list[JourneyPlannerBlockerCode] = []
        if pattern.name.startswith("IMP"):
            international = next((leg for leg in legs if leg.role == LegRole.INTERNATIONAL_IMPORT), None)
            if not international or international.destination_code != PNG_GATEWAY_CODE:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID)
        if pattern.name.startswith("EXP"):
            international = next((leg for leg in legs if leg.role == LegRole.INTERNATIONAL_EXPORT), None)
            if not international or international.origin_code != PNG_GATEWAY_CODE:
                blockers.append(JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID)
        return blockers

    def _automation_blockers(self, pattern: JourneyPattern) -> list[JourneyPlannerBlockerCode]:
        if pattern == JourneyPattern.EXP_HGU:
            return [JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED]
        return []

    @staticmethod
    def _dedupe(blockers: list[JourneyPlannerBlockerCode]) -> list[JourneyPlannerBlockerCode]:
        seen: set[JourneyPlannerBlockerCode] = set()
        unique: list[JourneyPlannerBlockerCode] = []
        for blocker in blockers:
            if blocker not in seen:
                unique.append(blocker)
                seen.add(blocker)
        return unique
