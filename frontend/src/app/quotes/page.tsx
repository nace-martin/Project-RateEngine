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
import { Search, Plus, Filter, Loader2 } from "lucide-react";
import { StandardPageContainer, PageHeader } from "@/components/layout/standard-page";
import { DataTable } from "@/components/ui/data-table-wrapper";
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";

import { UnifiedQuote, formatCurrency, formatRoute, formatDate, getWeight, getCustomerName } from "@/lib/quote-helpers";

// --- Helpers -> Removed (imported from lib/quote-helpers)


// --- Main Component ---

export default function QuotesPage() {
  const { user } = useAuth();
  const { canEditQuotes, isFinance } = usePermissions();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

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
      return <Badge variant="secondary" className="bg-amber-100 text-amber-800 hover:bg-amber-100">Draft (SPOT)</Badge>;
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
        weight: getWeight(q),
        status: q.status,
        rawStatus: q.status,
        total: formatCurrency(totalAmt, currency),
        actionLink: `/quotes/${q.id}`,
      });
    });

    // 2. Map Spot Drafts
    spotDrafts.forEach(d => {
      unified.push({
        id: d.id,
        type: "SPOT_DRAFT",
        number: "SPOT Draft", // Or generate a placeholder like "DRAFT-..."
        customer: "-", // Spot drafts dont have customer attached in the envelope usually
        route: `${d.shipment.origin_code} → ${d.shipment.destination_code}`,
        date: d.created_at,
        weight: `${d.shipment.total_weight_kg} kg`,
        status: "Draft",
        rawStatus: "DRAFT",
        total: "-",
        actionLink: `/quotes/spot/${d.id}`,
      });
    });

    // 3. Filter
    const query = searchQuery.toLowerCase();
    const filtered = unified.filter(item =>
      item.number.toLowerCase().includes(query) ||
      item.customer.toLowerCase().includes(query) ||
      item.route.toLowerCase().includes(query)
    );

    // 4. Sort (Date Descending)
    return filtered.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  }, [quotes, spotDrafts, searchQuery]);

  const columns = [
    {
      header: "Quote #",
      accessorKey: "number" as keyof UnifiedQuote,
      className: "font-medium text-primary",
    },
    {
      header: "Date",
      cell: (item: UnifiedQuote) => formatDate(item.date),
      className: "text-muted-foreground text-sm",
    },
    {
      header: "Customer",
      accessorKey: "customer" as keyof UnifiedQuote,
      className: "max-w-[200px] truncate",
    },
    {
      header: "Route",
      accessorKey: "route" as keyof UnifiedQuote,
    },
    {
      header: "Weight",
      accessorKey: "weight" as keyof UnifiedQuote,
      className: "text-right font-mono text-xs",
    },
    {
      header: "Status",
      cell: (item: UnifiedQuote) => getStatusBadge(item),
    },
    {
      header: "Total (Inc. GST)",
      accessorKey: "total" as keyof UnifiedQuote,
      className: "text-right font-medium",
    },
    {
      header: "",
      cell: (item: UnifiedQuote) => (
        <Button
          variant="ghost"
          size="sm"
          asChild
          className={item.type === "SPOT_DRAFT" ? "text-amber-600 hover:text-amber-700 hover:bg-amber-50" : ""}
        >
          <Link href={item.actionLink}>
            {item.type === "SPOT_DRAFT" ? "Resume" : "View"}
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
        actions={
          canEditQuotes && (
            <Button asChild className="bg-primary hover:bg-primary/90">
              <Link href="/quotes/new">
                <Plus className="h-4 w-4 mr-2" />
                New Quote
              </Link>
            </Button>
          )
        }
      />

      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            type="search"
            placeholder="Search quotes..."
            className="pl-9 bg-background"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        {/* Future: Add more detailed filters here if needed */}
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
          emptyMessage="No quotes found matching your search."
          onRowClick={(item) => router.push(item.actionLink)}
        />
      )}
    </StandardPageContainer>
  );
}
