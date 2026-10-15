"""Policy-versioned FX side and CAF conventions (CommercialTermsPolicy.caf_method / fx_side_convention).

Stored FX is normalized to PGK per 1 FCY with the BSP bank side kept:
    stored TT BUY  = 1 / published TT Buy   (published as FCY per 1 PGK)
    stored TT SELL = 1 / published TT Sell

Approved BSP rule (BSP calculator, confirmed 2026-10-14):
    FCY -> PGK uses TT BUY.  PGK = FCY / (published TT Buy x (1 - CAF)) = FCY x stored TT BUY / (1 - CAF)
                             (import CAF reduces the published rate; it is not an uplift on the amount)
    PGK -> FCY uses TT SELL. FCY = (PGK x published TT Sell) x (1 + CAF) = (PGK / stored TT SELL) x (1 + CAF)
                             (CAF is a separate uplift after pure conversion; no conversion, no CAF)

Superseded (Pilot Gate B3L-B, policy COMMERCIAL-POLICY-2026-10-11): ``UPLIFT_AFTER_FX`` with
``COST_AT_TT_SELL`` priced FCY -> PGK at TT SELL and PGK -> FCY at TT BUY. Those sides are wrong; a
policy carrying them is not edited in place, but a conversion under it fails closed.
"""

from __future__ import annotations

from decimal import Decimal

from pricing_v4.services.commercial_policy import MissingCommercialPolicyError

CAF_LEGACY = "LEGACY_RATE_ADJUSTMENT"
CAF_SUPERSEDED_UPLIFT = "UPLIFT_AFTER_FX"
CAF_APPROVED = "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT"

FX_LEGACY = "LEGACY_COST_AT_TT_BUY"
FX_SUPERSEDED = "COST_AT_TT_SELL"
FX_APPROVED = "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL"

# Methods whose conversions are recorded by the engine (as opposed to the legacy rate adjustment).
ENGINE_CONVERSION_CAF_METHODS = frozenset({CAF_SUPERSEDED_UPLIFT, CAF_APPROVED})

SIDE_FCY_TO_PGK = "TT_BUY"
SIDE_PGK_TO_FCY = "TT_SELL"
CAF_OPERATION_TO_PGK = "PUBLISHED_RATE_REDUCED"
CAF_OPERATION_FROM_PGK = "UPLIFTED_AFTER_FX"


class SupersededFxConventionError(MissingCommercialPolicyError):
    """The resolved policy carries an FX side convention that is no longer approved."""


def uses_engine_conversions(caf_method: str | None) -> bool:
    return caf_method in ENGINE_CONVERSION_CAF_METHODS


def require_approved_convention(caf_method: str | None, fx_side_convention: str | None) -> None:
    """Fail closed unless the policy carries the approved BSP sides and CAF methods together."""
    if caf_method == CAF_APPROVED and fx_side_convention == FX_APPROVED:
        return
    raise SupersededFxConventionError(
        f"Commercial policy convention ({caf_method}, {fx_side_convention}) is not the approved BSP FX rule "
        f"({CAF_APPROVED}, {FX_APPROVED}); a currency conversion under it fails closed."
    )


def fcy_to_pgk_rate(stored_tt_buy: Decimal, caf_rate: Decimal) -> Decimal:
    """PGK per FCY after the import CAF reduces the published TT Buy: stored TT BUY / (1 - CAF)."""
    divisor = Decimal("1") - caf_rate
    if divisor <= 0:
        raise MissingCommercialPolicyError("Import CAF must be below 100% to reduce the FX rate.")
    return stored_tt_buy / divisor
