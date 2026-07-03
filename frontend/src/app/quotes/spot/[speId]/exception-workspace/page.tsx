"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { getDraftQuote } from "../../../../../lib/api";
import { DraftQuote } from "../../../../../lib/draft-quote-types";
import { ExceptionWorkspace } from "../../../../../components/spot/ExceptionWorkspace";
import { Loader2, AlertCircle, ArrowLeft, RefreshCw } from "lucide-react";

export default function ExceptionWorkspaceLivePage() {
  const params = useParams();
  const router = useRouter();
  const speId = params?.speId as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DraftQuote | null>(null);

  const fetchQuote = useCallback(async () => {
    if (!speId) return;
    setLoading(true);
    setError(null);
    try {
      const payload = await getDraftQuote(speId);
      setData(payload);
    } catch (err) {
      console.error("Error fetching live draft quote:", err);
      const errObject = err as Error;
      const errMsg = errObject.message || "";
      if (errMsg.includes("401") || errMsg.includes("Authentication token")) {
        setError("You must be logged in to view this exception workspace. Please log in first.");
      } else if (errMsg.includes("404") || errMsg.includes("matches the given query")) {
        setError("Spot Pricing Envelope not found, or you do not have permission to access it.");
      } else if (errMsg.includes("403")) {
        setError("You do not have permission to view this exception workspace.");
      } else {
        setError(errMsg || "Failed to load live draft quote. Please try again later.");
      }
    } finally {
      setLoading(false);
    }
  }, [speId]);

  useEffect(() => {
    fetchQuote();
  }, [fetchQuote]);

  const handleGoBack = () => {
    if (speId) {
      router.push(`/quotes/spot/${speId}`);
    } else {
      router.back();
    }
  };

  if (loading) {
    return (
      <div className="w-full min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-200 p-6">
        <div className="flex flex-col items-center gap-4 max-w-md text-center">
          <Loader2 className="w-12 h-12 text-indigo-500 animate-spin" />
          <h2 className="text-xl font-bold">Loading Live Draft Quote...</h2>
          <p className="text-sm text-slate-400">
            Fetching extracted supplier rate structures and catalog validation rules from the backend.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-200 p-6">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 max-w-lg w-full shadow-2xl flex flex-col items-center text-center gap-6">
          <div className="bg-rose-950/40 border border-rose-900/60 p-4 rounded-full text-rose-400">
            <AlertCircle className="w-10 h-10" />
          </div>
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-bold text-slate-50">Intake Sync Failed</h2>
            <p className="text-sm text-slate-400">{error}</p>
          </div>
          <div className="flex gap-3 w-full mt-2">
            <button
              onClick={handleGoBack}
              className="flex-1 inline-flex justify-center items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 transition text-sm font-medium text-slate-200"
            >
              <ArrowLeft className="w-4 h-4" />
              Go Back
            </button>
            <button
              onClick={fetchQuote}
              className="flex-1 inline-flex justify-center items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 transition text-sm font-medium text-white shadow-lg shadow-indigo-600/20"
            >
              <RefreshCw className="w-4 h-4" />
              Retry Connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="w-full min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-200 p-6">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 max-w-lg w-full shadow-2xl flex flex-col items-center text-center gap-6">
          <div className="bg-slate-800 p-4 rounded-full text-slate-400">
            <AlertCircle className="w-10 h-10" />
          </div>
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-bold text-slate-50">Empty Draft Quote</h2>
            <p className="text-sm text-slate-400">No data could be retrieved for this Spot Envelope.</p>
          </div>
          <button
            onClick={handleGoBack}
            className="w-full inline-flex justify-center items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 transition text-sm font-medium text-slate-200"
          >
            <ArrowLeft className="w-4 h-4" />
            Go Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen bg-slate-950">
      <ExceptionWorkspace initialData={data} isLive={true} envelopeId={speId} />
    </div>
  );
}
