import { notFound } from "next/navigation";

type PublicQuoteLine = {
  description: string;
  source: string;
  sell: string;
  is_informational: boolean;
};

type PublicQuoteBucket = {
  name: string;
  subtotal: string;
  lines: PublicQuoteLine[];
};

type PublicQuoteResponse = {
  quote_number: string;
  status: string;
  created_at: string;
  valid_until: string | null;
  customer: {
    name: string;
    contact: string | null;
  };
  shipment: {
    mode: string;
    direction: string;
    incoterm: string | null;
    payment_term: string | null;
  };
  route: {
    origin_code: string;
    origin_name: string;
    destination_code: string;
    destination_name: string;
  };
  currency: string;
  totals: {
    sell_excl_gst: string;
    gst: string;
    sell_incl_gst: string;
    fcy: boolean | null;
    fcy_currency: string | null;
    fcy_amount: string | null;
  };
  charge_buckets: PublicQuoteBucket[];
};

const formatMoney = (currency: string, value: string | number | null) => {
  if (value === null || value === undefined) {
    return `${currency} 0.00`;
  }
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) {
    return `${currency} ${value}`;
  }
  return `${currency} ${amount.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

type PublicQuotePageProps = {
  searchParams?: {
    token?: string | string[];
    version?: string | string[];
    summary?: string | string[];
  };
};

export default async function PublicQuotePage({ searchParams }: PublicQuotePageProps) {
  const tokenParam = searchParams?.token;
  const token = Array.isArray(tokenParam) ? tokenParam[0] : tokenParam;
  const versionParam = searchParams?.version;
  const version = Array.isArray(versionParam) ? versionParam[0] : versionParam;
  const summaryParam = searchParams?.summary;
  const summaryValue = Array.isArray(summaryParam) ? summaryParam[0] : summaryParam;
  const summaryOnly = summaryValue ? ["1", "true", "yes"].includes(summaryValue.toLowerCase()) : false;
  if (!token) {
    notFound();
  }

  const rawApiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const apiBase = rawApiBase.toLowerCase().endsWith('/api') ? rawApiBase.slice(0, -4) : rawApiBase;
  const params = new URLSearchParams({ token });
  if (version) {
    params.set("version", version);
  }
  if (summaryOnly) {
    params.set("summary", "1");
  }
  const response = await fetch(`${apiBase}/api/v3/quotes/public/?${params.toString()}`, {
    cache: "no-store",
  });

  if (response.status === 404) {
    notFound();
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message =
      detail && typeof detail === "object" && "detail" in detail && typeof detail.detail === "string"
        ? detail.detail
        : "This shared link is invalid or has expired.";
    return (
      <main className="min-h-screen bg-slate-50">
        <div className="mx-auto max-w-3xl px-4 py-12">
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Quote Share</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900">Link unavailable</h1>
            <p className="mt-3 text-sm text-slate-600">{message}</p>
          </div>
        </div>
      </main>
    );
  }

  const data = (await response.json()) as PublicQuoteResponse;

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-4xl px-4 py-10 space-y-6">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-400">Quote</p>
              <h1 className="mt-2 text-3xl font-semibold text-slate-900">{data.quote_number}</h1>
              <p className="mt-2 text-sm text-slate-500">
                Created {new Date(data.created_at).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })}
              </p>
              <p className="text-sm text-slate-500">
                Valid until {data.valid_until ? new Date(data.valid_until).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "N/A"}
              </p>
            </div>
            <div className="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
              {data.status}
            </div>
          </div>
          <div className="mt-6 grid gap-4 rounded-xl border border-slate-100 bg-slate-50 p-4 md:grid-cols-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Customer</p>
              <p className="mt-1 text-base font-semibold text-slate-800">{data.customer.name}</p>
              {data.customer.contact && (
                <p className="text-sm text-slate-500">Contact: {data.customer.contact}</p>
              )}
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Shipment</p>
              <p className="mt-1 text-base font-semibold text-slate-800">
                {data.shipment.mode} / {data.shipment.direction}
              </p>
              <p className="text-sm text-slate-500">
                Payment: {data.shipment.payment_term || "N/A"}
              </p>
              {data.shipment.incoterm && (
                <p className="text-sm text-slate-500">Incoterm: {data.shipment.incoterm}</p>
              )}
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Route</p>
          <div className="mt-4 flex flex-col items-center gap-4 text-center md:flex-row md:justify-between">
            <div>
              <p className="text-3xl font-semibold text-slate-900">{data.route.origin_code}</p>
              <p className="text-sm text-slate-500">{data.route.origin_name}</p>
            </div>
            <div className="text-sm font-semibold uppercase tracking-[0.3em] text-rose-500">to</div>
            <div>
              <p className="text-3xl font-semibold text-slate-900">{data.route.destination_code}</p>
              <p className="text-sm text-slate-500">{data.route.destination_name}</p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Totals</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Excl. GST</p>
              <p className="mt-2 text-lg font-semibold text-slate-900">
                {formatMoney(data.currency, data.totals.sell_excl_gst)}
              </p>
            </div>
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">GST (10%)</p>
              <p className="mt-2 text-lg font-semibold text-slate-900">
                {formatMoney(data.currency, data.totals.gst)}
              </p>
            </div>
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Grand Total</p>
              <p className="mt-2 text-lg font-semibold text-slate-900">
                {formatMoney(data.currency, data.totals.sell_incl_gst)}
              </p>
            </div>
          </div>
          {data.totals.fcy && data.totals.fcy_currency && data.totals.fcy_amount && (
            <p className="mt-3 text-sm text-slate-500">
              Equivalent: {formatMoney(data.totals.fcy_currency, data.totals.fcy_amount)}
            </p>
          )}
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
              {summaryOnly ? "Pricing Summary" : "Charge Breakdown"}
            </p>
            <p className="text-xs text-slate-400">Link valid for 7 days</p>
          </div>
          <div className="mt-4 space-y-4">
            {data.charge_buckets.map((bucket) => (
              <div key={bucket.name} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                  <span className="text-sm font-semibold text-slate-900">{bucket.name}</span>
                  <span className="text-sm font-semibold text-slate-700">
                    {formatMoney(data.currency, bucket.subtotal)}
                  </span>
                </div>
                {!summaryOnly && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm text-slate-600">
                      <thead className="text-xs uppercase tracking-wide text-slate-400">
                        <tr>
                          <th className="pb-2">Description</th>
                          <th className="pb-2 text-right">Amount ({data.currency})</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bucket.lines.map((line, index) => (
                          <tr key={`${bucket.name}-${index}`} className={line.is_informational ? "text-slate-400" : ""}>
                            <td className="py-2 pr-4">{line.description}</td>
                            <td className="py-2 text-right">{formatMoney(data.currency, line.sell)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
            {data.charge_buckets.length === 0 && (
              <p className="text-sm text-slate-500">No charge lines available.</p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
