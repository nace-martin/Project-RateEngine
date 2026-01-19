"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import { getQuotesV3, listSpotEnvelopes } from "@/lib/api";
import { V3QuoteComputeResponse } from "@/lib/types";
import { SpotPricingEnvelope } from "@/lib/spot-types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Search, Plus, Filter, Loader2, FileText, Save } from "lucide-react";
import { StandardPageContainer, PageHeader } from "@/components/layout/standard-page";
import { DataTable } from "@/components/ui/data-table-wrapper";
import { EmptyState } from "@/components/ui/empty-state";
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";
import { QuoteQuickLook } from "@/components/QuoteQuickLook";

import { UnifiedQuote, formatCurrency, formatRoute, formatDate, getWeight, getCustomerName, calculateSpotTotal } from "@/lib/quote-helpers";

// --- Main Component ---

export default function QuotesPage() {
  const { user } = useAuth();
  const { canEditQuotes, isFinance } = usePermissions();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [modeFilter, setModeFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Quick Look State
  const [selectedQuote, setSelectedQuote] = useState<UnifiedQuote | null>(null);
  const [isQuickLookOpen, setIsQuickLookOpen] = useState(false);

  // Raw Data
  const [quotes, setQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [spotDrafts, setSpotDrafts] = useState<SpotPricingEnvelope[]>([]);

  useEffect(() => {
    if (user) {
      const fetchData = async () => {
        setLoading(true);
        try {
          const [quotesData, draftsData] = await Promise.all([
            getQuotesV3({}), // Fetch all, handle filtering client-side for now for unified search
            listSpotEnvelopes('draft').catch(() => []),
          ]);
          setQuotes(quotesData.results);
          setSpotDrafts(draftsData);
        } catch (err) {
          console.error("Failed to fetch quotes", err);
        } finally {
          setLoading(false);
        }
      };
      fetchData();
    }
  }, [user]);

  // specific status badges for spot drafts
  const getStatusBadge = (item: UnifiedQuote) => {
    if (item.type === "SPOT_DRAFT") {
      return <Badge variant="secondary" className="bg-amber-500 text-white border-amber-600 hover:bg-amber-500">Draft (SPOT)</Badge>;
    }
    return <QuoteStatusBadge status={item.rawStatus} />;
  };

  // Unified Data
  const tableData = useMemo<UnifiedQuote[]>(() => {
    const unified: UnifiedQuote[] = [];

    // 1. Map Standard Quotes
    quotes.forEach(q => {
      const totalAmt = q.latest_version?.totals?.total_sell_fcy_incl_gst;
      const currency = q.latest_version?.totals?.total_sell_fcy_currency;

      unified.push({
        id: q.id,
        type: "STANDARD",
        number: q.quote_number,
        customer: getCustomerName(q.customer),
        route: `${formatRoute(q.origin_location)} → ${formatRoute(q.destination_location)}`,
        date: q.created_at,
        expiry: q.valid_until, // Standard quotes have valid_until field
        weight: getWeight(q),
        status: q.status,
        rawStatus: q.status,
        total: formatCurrency(totalAmt, currency),
        actionLink: `/quotes/${q.id}`,
        mode: q.mode || "AIR",
        serviceType: q.shipment_type || "Import",
        incoterms: q.incoterm || "-",
        scope: q.service_scope || "-",
        createdBy: q.created_by || "Unknown"
      });
    });

    // 2. Map Spot Drafts
    spotDrafts.forEach(d => {
      // Create a prettier ID display - use "SQ-" (Spot Quote) + first 6 chars for consistency with QT-
      const shortId = d.id.substring(0, 6).toUpperCase();

      unified.push({
        id: d.id,
        type: "SPOT_DRAFT",
        number: `SQ-${shortId}`,
        customer: d.customer_name || "Spot Request",
        route: `${formatRoute(d.shipment.origin_code)} → ${formatRoute(d.shipment.destination_code)}`,
        date: d.created_at,
        expiry: d.expires_at,
        weight: `${d.shipment.total_weight_kg} kg`,
        status: "Draft",
        rawStatus: "DRAFT",
        total: calculateSpotTotal(d),
        actionLink: `/quotes/spot/${d.id}`,
        mode: "AIR", // Implicitly AIR
        serviceType: "Spot Request",
        incoterms: "-",
        scope: "-",
        createdBy: "User"
      });
    });

    // 3. Filter by search query and mode
    const query = searchQuery.toLowerCase();
    const filtered = unified.filter(item => {
      const matchesSearch = item.number.toLowerCase().includes(query) ||
        item.customer.toLowerCase().includes(query) ||
        item.route.toLowerCase().includes(query);

      const matchesMode = modeFilter === "all" || item.mode === modeFilter;
      const matchesStatus = statusFilter === "all" || item.rawStatus === statusFilter;

      return matchesSearch && matchesMode && matchesStatus;
    });

    // 4. Sort (Date Descending)
    return filtered.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  }, [quotes, spotDrafts, searchQuery, modeFilter, statusFilter]);

  const columns = [
    {
      header: "Quote #",
      accessorKey: "number" as keyof UnifiedQuote,
      className: "font-medium text-primary w-[140px]",
    },
    {
      header: "Date",
      cell: (item: UnifiedQuote) => {
        // Only show expiry if within 48 hours
        const showExpiry = item.expiry &&
          (new Date(item.expiry).getTime() - Date.now()) < (48 * 60 * 60 * 1000);

        return (
          <div className="flex flex-col">
            <span>{formatDate(item.date)}</span>
            {showExpiry && (
              <span className="text-xs text-amber-600 font-medium flex items-center gap-1">
                <span className="inline-block w-1.5 h-1.5 bg-amber-500 rounded-full animate-pulse"></span>
                EXP: {formatDate(item.expiry as string)}
              </span>
            )}
          </div>
        );
      },
      className: "text-muted-foreground text-sm",
    },
    {
      header: "Customer",
      accessorKey: "customer" as keyof UnifiedQuote,
      className: "max-w-[200px] truncate font-medium",
    },
    {
      header: "Route",
      accessorKey: "route" as keyof UnifiedQuote,
      className: "min-w-[150px]",
    },
    {
      header: "Mode",
      accessorKey: "mode" as keyof UnifiedQuote,
      className: "w-[80px] text-sm font-medium text-slate-600",
    },
    {
      header: "Weight",
      accessorKey: "weight" as keyof UnifiedQuote,
      className: "text-right w-[100px]",
      headerClassName: "text-right",
    },
    {
      header: "Status",
      cell: (item: UnifiedQuote) => getStatusBadge(item),
      className: "w-[120px]",
    },
    {
      header: "User",
      accessorKey: "createdBy" as keyof UnifiedQuote,
      className: "text-muted-foreground text-sm w-[100px]",
    },
    {
      header: "Total",
      accessorKey: "total" as keyof UnifiedQuote,
      className: "text-right font-medium tabular-nums min-w-[120px]",
      headerClassName: "text-right",
    },
    {
      header: "",
      cell: (item: UnifiedQuote) => (
        <Button
          variant="outline"
          size="sm"
          asChild
          className="w-20 border-slate-200 hover:bg-slate-50 text-slate-700 h-8"
        >
          <Link href={item.actionLink}>
            {["DRAFT", "draft"].includes(item.rawStatus) ? "Resume" : "View"}
          </Link>
        </Button>
      ),
      className: "text-right w-[100px]",
    }
  ];

  if (!user) return null;

  return (
    <StandardPageContainer>
      <PageHeader
        title={isFinance ? "Quotes Register" : "Quotes Dashboard"}
        description="Manage and track all logistics quotes."
      />

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Search by quote #, customer, or route..."
            className="pl-9 bg-background"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <select
            value={modeFilter}
            onChange={(e) => setModeFilter(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="all">All Modes</option>
            <option value="AIR">Air Freight</option>
            <option value="SEA">Sea Freight</option>
            <option value="ROAD">Road/Inland</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            <option value="all">All Statuses</option>
            <option value="DRAFT">Draft</option>
            <option value="FINALIZED">Finalized</option>
            <option value="SENT">Sent</option>
            <option value="ACCEPTED">Accepted (Won)</option>
            <option value="LOST">Lost</option>
            <option value="EXPIRED">Expired</option>
          </select>
          <Button variant="outline" size="sm" className="h-9 gap-2 text-muted-foreground hover:text-primary">
            <Save className="h-4 w-4" />
            <span className="hidden sm:inline">Save View</span>
          </Button>
        </div>
      </div>

      <div className="text-sm text-muted-foreground">
        Showing {tableData.length} of {quotes.length + spotDrafts.length} quotes
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : (
        <DataTable
          data={tableData}
          columns={columns}
          keyExtractor={(item) => item.id}
          emptyState={
            <EmptyState
              title="No quotes found"
              description={searchQuery ? "No quotes match your search criteria." : "You haven't created any quotes yet."}
              icon={FileText}
              actionLabel={searchQuery ? "Clear Search" : "Create New Quote"}
              onAction={searchQuery ? () => setSearchQuery("") : () => router.push("/quotes/new")}
              className="py-12 border-none"
            />
          }
          onRowClick={(item) => {
            setSelectedQuote(item);
            setIsQuickLookOpen(true);
          }}
        />
      )}

      {/* Quick Look Drawer */}
      <QuoteQuickLook
        open={isQuickLookOpen}
        onOpenChange={setIsQuickLookOpen}
        quote={selectedQuote}
      />
    </StandardPageContainer>
  );
}
