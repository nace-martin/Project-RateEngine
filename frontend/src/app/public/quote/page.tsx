import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { ArrowRight, CalendarDays, Globe2, Mail, MapPin, Phone, Plane, ReceiptText, ShieldCheck } from "lucide-react";
import { API_BASE_URL } from "@/lib/config";
import { formatIncoterm, formatPaymentTerm, formatServiceScope } from "@/lib/display";
import { PublicQuoteActions } from "./PublicQuoteActions";

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
  branding: {
    display_name: string;
    support_email: string;
    support_phone: string;
    website_url: string;
    address_lines: string[];
    public_quote_tagline: string;
    primary_color: string;
    accent_color: string;
    logo_url: string | null;
  };
  customer: {
    name: string;
    contact: string | null;
  };
  shipment: {
    mode: string;
    direction: string;
    service_scope: string | null;
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

const formatDate = (value: string | null) => {
  if (!value) return "N/A";
  return new Date(value).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

const withAlpha = (hex: string, alphaHex: string) => {
  const value = (hex || "").trim();
  if (!/^#[0-9A-Fa-f]{6}$/.test(value)) {
    return undefined;
  }
  return `${value}${alphaHex}`;
};

const statusLabel = (status: string) =>
  status
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());

const bucketLabel = (name: string) => (name === "Freight" ? "International Freight" : name);

type PublicQuoteSearchParams = {
  token?: string | string[];
  version?: string | string[];
  summary?: string | string[];
};

type PublicQuotePageProps = {
  searchParams?: Promise<PublicQuoteSearchParams>;
};

function DetailItem({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-950">{value || "N/A"}</div>
    </div>
  );
}

function ContactItem({
  icon,
  value,
}: {
  icon: ReactNode;
  value: string | null | undefined;
}) {
  if (!value) return null;
  return (
    <div className="inline-flex items-center gap-2 text-sm text-slate-600">
      <span className="text-slate-400">{icon}</span>
      <span>{value}</span>
    </div>
  );
}

export default async function PublicQuotePage({ searchParams }: PublicQuotePageProps) {
  const resolvedSearchParams = await searchParams;
  const tokenParam = resolvedSearchParams?.token;
  const token = Array.isArray(tokenParam) ? tokenParam[0] : tokenParam;
  const versionParam = resolvedSearchParams?.version;
  const version = Array.isArray(versionParam) ? versionParam[0] : versionParam;
  const summaryParam = resolvedSearchParams?.summary;
  const summaryValue = Array.isArray(summaryParam) ? summaryParam[0] : summaryParam;
  const summaryOnly = summaryValue ? ["1", "true", "yes"].includes(summaryValue.toLowerCase()) : false;
  if (!token) {
    notFound();
  }

  const apiBase = API_BASE_URL;
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
      <main className="min-h-screen bg-slate-100">
        <div className="mx-auto max-w-3xl px-4 py-12">
          <div className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
            <p className="text-sm font-semibold text-slate-500">Quote Share</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">Link unavailable</h1>
            <p className="mt-3 text-sm text-slate-600">{message}</p>
          </div>
        </div>
      </main>
    );
  }

  const data = (await response.json()) as PublicQuoteResponse;
  const normalizedScope = (data.shipment.service_scope || "").toUpperCase();
  const showAirportReferences = ["A2D", "D2A", "A2A", "P2P"].includes(normalizedScope);
  const brandPrimary = data.branding.primary_color || "#0F2A56";
  const brandAccent = data.branding.accent_color || "#D71920";
  const primarySoft = withAlpha(brandPrimary, "10") || "#eef2ff";
  const primaryBorder = withAlpha(brandPrimary, "24") || "#cbd5e1";
  const accentSoft = withAlpha(brandAccent, "12") || "#fff1f2";
  const accentBorder = withAlpha(brandAccent, "33") || "#fecaca";
  const statusText = statusLabel(data.status);
  const chargeLineCount = data.charge_buckets.reduce((total, bucket) => total + bucket.lines.length, 0);

  return (
    <main className="min-h-screen bg-[#f3f6fa] text-slate-950">
      <div className="h-3" style={{ backgroundColor: brandPrimary }} />

      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-5 py-5 sm:px-8">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-4">
                  {data.branding.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={data.branding.logo_url}
                      alt={data.branding.display_name}
                      className="h-12 w-auto max-w-[220px] object-contain"
                    />
                  ) : (
                    <div
                      className="flex h-12 w-12 items-center justify-center rounded-md text-base font-bold text-white"
                      style={{ backgroundColor: brandPrimary }}
                    >
                      {data.branding.display_name.slice(0, 1).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <div className="text-base font-semibold text-slate-950">{data.branding.display_name}</div>
                    {data.branding.public_quote_tagline ? (
                      <div className="text-sm text-slate-500">{data.branding.public_quote_tagline}</div>
                    ) : null}
                  </div>
                </div>

                <div className="mt-6 flex flex-wrap items-center gap-3">
                  <h1 className="text-3xl font-semibold text-slate-950 sm:text-4xl">{data.quote_number}</h1>
                  <span
                    className="inline-flex h-8 items-center rounded-full border px-3 text-xs font-semibold"
                    style={{ borderColor: accentBorder, backgroundColor: accentSoft, color: brandAccent }}
                  >
                    {statusText}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-600">
                  <span className="inline-flex items-center gap-2">
                    <CalendarDays className="h-4 w-4 text-slate-400" aria-hidden="true" />
                    Created {formatDate(data.created_at)}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-slate-400" aria-hidden="true" />
                    Valid until {formatDate(data.valid_until)}
                  </span>
                </div>
              </div>

              <div className="w-full rounded-lg border border-slate-200 bg-slate-50 p-5 lg:w-[340px]">
                <div className="text-sm font-semibold text-slate-600">Grand Total</div>
                <div className="mt-2 text-3xl font-semibold text-slate-950">
                  {formatMoney(data.currency, data.totals.sell_incl_gst)}
                </div>
                <div className="mt-2 text-sm text-slate-500">
                  Includes GST of {formatMoney(data.currency, data.totals.gst)}
                </div>
                <div className="mt-5">
                  <PublicQuoteActions
                    quoteNumber={data.quote_number}
                    supportEmail={data.branding.support_email}
                    brandPrimary={brandPrimary}
                    brandAccent={brandAccent}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="grid border-b border-slate-200 lg:grid-cols-[1.15fr_0.85fr]">
            <section className="border-b border-slate-200 px-5 py-6 sm:px-8 lg:border-b-0 lg:border-r">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <MapPin className="h-4 w-4" style={{ color: brandAccent }} aria-hidden="true" />
                Route
              </div>
              <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
                <div>
                  <div className="text-4xl font-semibold text-slate-950 sm:text-5xl">{data.route.origin_code}</div>
                  <div className="mt-2 text-sm text-slate-600">{showAirportReferences ? data.route.origin_name : "Origin"}</div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="hidden h-px w-16 bg-slate-300 sm:block" />
                  <span
                    className="flex h-10 w-10 items-center justify-center rounded-full border bg-white"
                    style={{ borderColor: primaryBorder }}
                  >
                    <Plane className="h-4 w-4" style={{ color: brandPrimary }} aria-hidden="true" />
                  </span>
                  <ArrowRight className="hidden h-4 w-4 text-slate-400 sm:block" aria-hidden="true" />
                </div>
                <div className="text-right">
                  <div className="text-4xl font-semibold text-slate-950 sm:text-5xl">{data.route.destination_code}</div>
                  <div className="mt-2 text-sm text-slate-600">{showAirportReferences ? data.route.destination_name : "Destination"}</div>
                </div>
              </div>
            </section>

            <section className="px-5 py-6 sm:px-8">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <ReceiptText className="h-4 w-4" style={{ color: brandAccent }} aria-hidden="true" />
                Quote Details
              </div>
              <div className="mt-5 grid grid-cols-2 gap-5">
                <DetailItem label="Customer" value={data.customer.name} />
                <DetailItem label="Contact" value={data.customer.contact} />
                <DetailItem label="Shipment" value={[data.shipment.mode, data.shipment.direction].filter(Boolean).join(" / ")} />
                <DetailItem label="Payment" value={formatPaymentTerm(data.shipment.payment_term)} />
                <DetailItem label="Service Scope" value={formatServiceScope(data.shipment.service_scope)} />
                <DetailItem label="Incoterm" value={data.shipment.incoterm ? formatIncoterm(data.shipment.incoterm) : "N/A"} />
              </div>
            </section>
          </div>

          <section className="border-b border-slate-200 px-5 py-6 sm:px-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-slate-950">Totals</h2>
                <p className="mt-1 text-sm text-slate-500">{chargeLineCount} charge lines across {data.charge_buckets.length} categories</p>
              </div>
              {data.totals.fcy && data.totals.fcy_currency && data.totals.fcy_amount ? (
                <div className="text-sm text-slate-500">
                  Equivalent: <span className="font-semibold text-slate-800">{formatMoney(data.totals.fcy_currency, data.totals.fcy_amount)}</span>
                </div>
              ) : null}
            </div>
            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="text-sm font-semibold text-slate-500">Total Excl. GST</div>
                <div className="mt-2 text-xl font-semibold text-slate-950">{formatMoney(data.currency, data.totals.sell_excl_gst)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="text-sm font-semibold text-slate-500">GST</div>
                <div className="mt-2 text-xl font-semibold text-slate-950">{formatMoney(data.currency, data.totals.gst)}</div>
              </div>
              <div className="rounded-lg border p-4" style={{ borderColor: primaryBorder, backgroundColor: primarySoft }}>
                <div className="text-sm font-semibold" style={{ color: brandPrimary }}>Amount Payable</div>
                <div className="mt-2 text-2xl font-semibold text-slate-950">{formatMoney(data.currency, data.totals.sell_incl_gst)}</div>
              </div>
            </div>
          </section>

          <section className="px-5 py-6 sm:px-8">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-slate-950">
                  {summaryOnly ? "Pricing Summary" : "Charge Breakdown"}
                </h2>
                <p className="mt-1 text-sm text-slate-500">Amounts are shown in {data.currency}</p>
              </div>
              <div className="text-sm text-slate-500">Shared quote link valid for 7 days</div>
            </div>

            <div className="mt-5 overflow-hidden rounded-lg border border-slate-200">
              {data.charge_buckets.map((bucket, bucketIndex) => (
                <div key={bucket.name} className={bucketIndex > 0 ? "border-t border-slate-200" : ""}>
                  <div className="flex flex-col gap-2 bg-slate-50 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <div className="text-base font-semibold text-slate-950">{bucketLabel(bucket.name)}</div>
                      <div className="text-sm text-slate-500">{bucket.lines.length} line{bucket.lines.length === 1 ? "" : "s"}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-semibold text-slate-500">Subtotal</div>
                      <div className="text-lg font-semibold text-slate-950">{formatMoney(data.currency, bucket.subtotal)}</div>
                    </div>
                  </div>

                  {!summaryOnly ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[560px] text-left text-sm">
                        <thead className="border-y border-slate-200 bg-white text-slate-500">
                          <tr>
                            <th className="px-4 py-3 font-semibold">Description</th>
                            <th className="px-4 py-3 text-right font-semibold">Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {bucket.lines.map((line, index) => (
                            <tr key={`${bucket.name}-${index}`} className={line.is_informational ? "bg-slate-50 text-slate-500" : "text-slate-700"}>
                              <td className="px-4 py-3">
                                <div className="font-medium text-slate-800">{line.description}</div>
                                {line.is_informational ? (
                                  <div className="mt-1 inline-flex rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-500">
                                    Not included in subtotal
                                  </div>
                                ) : null}
                              </td>
                              <td className="whitespace-nowrap px-4 py-3 text-right font-semibold">
                                {formatMoney(data.currency, line.sell)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              ))}
              {data.charge_buckets.length === 0 ? (
                <div className="bg-white px-4 py-8 text-center text-sm text-slate-500">No charge lines available.</div>
              ) : null}
            </div>
          </section>

          <footer className="border-t border-slate-200 bg-slate-50 px-5 py-5 sm:px-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap gap-x-5 gap-y-2">
                <ContactItem icon={<Mail className="h-4 w-4" aria-hidden="true" />} value={data.branding.support_email} />
                <ContactItem icon={<Phone className="h-4 w-4" aria-hidden="true" />} value={data.branding.support_phone} />
                <ContactItem icon={<Globe2 className="h-4 w-4" aria-hidden="true" />} value={data.branding.website_url} />
              </div>
              <div className="text-sm text-slate-500">
                {data.branding.address_lines.length > 0 ? data.branding.address_lines.join(", ") : "Powered by RateEngine"}
              </div>
            </div>
          </footer>
        </section>

        <div className="pb-4 text-center text-xs text-slate-500">Powered by RateEngine</div>
      </div>
    </main>
  );
}
