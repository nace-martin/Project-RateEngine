"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowRight, Loader2, Route } from "lucide-react";

import { apiClient } from "../../../lib/api";

interface BusinessMovementOption {
  journey_revision: number;
  leg_id: string;
  leg_key: string;
  sequence: number;
  role: string;
  origin_code: string;
  destination_code: string;
  product_code_domain: string;
  transport_mode: string;
  label: string;
}

interface ChargeMovementState {
  charge_line_id: string;
  assigned_leg_key: string | null;
  journey_revision: number;
  options: BusinessMovementOption[];
}

interface BusinessMovementResponse {
  charges: ChargeMovementState[];
}

export function BusinessMovementResolver({ chargeLineId }: { chargeLineId: string }) {
  const params = useParams<{ speId?: string }>();
  const envelopeId = params?.speId;
  const [chargeState, setChargeState] = useState<ChargeMovementState | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!envelopeId) {
      setLoading(false);
      return;
    }

    apiClient
      .get<BusinessMovementResponse>(`/api/v3/spot/envelopes/${envelopeId}/business-movements/`)
      .then((response) => {
        if (cancelled) return;
        const match = response.data.charges.find((item) => item.charge_line_id === chargeLineId) || null;
        setChargeState(match);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load business movements.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [chargeLineId, envelopeId]);

  if (loading) {
    return (
      <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
        <Loader2 className="h-3 w-3 animate-spin" /> Checking journey movement…
      </div>
    );
  }

  if (!chargeState || chargeState.assigned_leg_key || chargeState.options.length <= 1) {
    return null;
  }

  const assign = async (option: BusinessMovementOption) => {
    if (!envelopeId || savingKey) return;
    setSavingKey(option.leg_key);
    setError(null);
    try {
      await apiClient.post(`/api/v3/spot/envelopes/${envelopeId}/business-movements/`, {
        charge_line_id: chargeLineId,
        journey_revision: chargeState.journey_revision,
        leg_key: option.leg_key,
      });
      window.location.reload();
    } catch (err: unknown) {
      const responseMessage = (err as { response?: { data?: { error?: string; error_code?: string } } })?.response?.data;
      setError(
        responseMessage?.error
          ? `${responseMessage.error_code ? `${responseMessage.error_code}: ` : ""}${responseMessage.error}`
          : err instanceof Error
            ? err.message
            : "Unable to assign business movement.",
      );
      setSavingKey(null);
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-indigo-900/60 bg-indigo-950/20 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-indigo-200">
        <Route className="h-4 w-4" />
        What movement does this charge apply to?
      </div>
      <p className="mb-3 text-[11px] text-slate-400">
        Choose the business movement. RateEngine will derive the leg and ProductCode domain from the current journey.
      </p>
      <div className="flex flex-col gap-2">
        {chargeState.options.map((option) => (
          <button
            key={option.leg_key}
            type="button"
            disabled={Boolean(savingKey)}
            onClick={() => assign(option)}
            className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-left text-xs text-slate-200 transition hover:border-indigo-700 hover:bg-slate-900 disabled:opacity-50"
          >
            <span>
              <strong className="block text-slate-100">{option.label}</strong>
              <span className="text-[10px] text-slate-500">
                {option.product_code_domain} · {option.role.replaceAll("_", " ")}
              </span>
            </span>
            {savingKey === option.leg_key ? (
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            ) : (
              <ArrowRight className="h-4 w-4 text-indigo-400" />
            )}
          </button>
        ))}
      </div>
      {error ? <p className="mt-2 text-[11px] text-red-300">{error}</p> : null}
    </div>
  );
}
