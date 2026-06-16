"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { usePermissions } from "@/hooks/usePermissions";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Combobox } from "@/components/ui/combobox";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  getProductCodeRequests,
  approveProductCodeRequest,
  rejectProductCodeRequest,
  getProductCodes,
  ProductCodeOption,
  ProductCodeRequestResponse,
} from "@/lib/api";
import {
  Loader2,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Database,
} from "lucide-react";

export default function ProductCodeRequestsPage() {
  const { isAdmin } = usePermissions();

  const [requests, setRequests] = useState<ProductCodeRequestResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"PENDING" | "APPROVED" | "REJECTED" | "ALL">("PENDING");

  // Approval Modal state
  const [selectedRequest, setSelectedRequest] = useState<ProductCodeRequestResponse | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [productCodes, setProductCodes] = useState<ProductCodeOption[]>([]);
  const [loadingProductCodes, setLoadingProductCodes] = useState(false);
  const [selectedProductCodeId, setSelectedProductCodeId] = useState("");
  const [submittingAction, setSubmittingAction] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Approval mode toggle: LINK = Link existing, CREATE = Create new inline
  const [approveMode, setApproveMode] = useState<"LINK" | "CREATE">("LINK");

  // Create New Form fields
  const [newId, setNewId] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newDomain, setNewDomain] = useState("EXPORT");
  const [newCategory, setNewCategory] = useState("HANDLING");
  const [newIsGstApplicable, setNewIsGstApplicable] = useState(false);
  const [newGstTreatment, setNewGstTreatment] = useState("STANDARD");
  const [newGlRevenueCode, setNewGlRevenueCode] = useState("REVENUE-PENDING");
  const [newGlCostCode, setNewGlCostCode] = useState("COST-PENDING");
  const [newDefaultUnit, setNewDefaultUnit] = useState("SHIPMENT");

  // Rejection Modal state
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProductCodeRequests(
        statusFilter === "ALL" ? undefined : { status: statusFilter }
      );
      setRequests(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load requests.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    if (isAdmin) {
      void fetchRequests();
    }
  }, [isAdmin, fetchRequests]);

  // Load product codes for linking
  const loadProductCodes = async () => {
    setLoadingProductCodes(true);
    try {
      const data = await getProductCodes();
      setProductCodes(data);
    } catch (err) {
      console.error("Failed to load product codes", err);
    } finally {
      setLoadingProductCodes(false);
    }
  };

  // Suggest ID dynamically based on domain and existing productCodes
  useEffect(() => {
    if (!productCodes.length || !newDomain) return;
    let min = 1000, max = 1999;
    if (newDomain === "IMPORT") { min = 2000; max = 2999; }
    else if (newDomain === "DOMESTIC") { min = 3000; max = 3999; }

    const ids = productCodes
      .map(pc => Number(pc.id))
      .filter(id => !isNaN(id) && id >= min && id <= max);
    const nextId = ids.length > 0 ? Math.max(...ids) + 1 : min;
    setNewId(String(nextId <= max ? nextId : min));
  }, [newDomain, productCodes]);

  // Keep prefix and user input normalized on domain changes
  useEffect(() => {
    if (!newDomain) return;
    const prefix = newDomain === "EXPORT" ? "EXP-" : newDomain === "IMPORT" ? "IMP-" : "DOM-";
    
    if (newCode && newCode.length >= 4 && newCode[3] === '-') {
      const remaining = newCode.substring(4);
      setNewCode(`${prefix}${remaining}`);
    } else if (!newCode) {
      setNewCode(prefix);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newDomain]);

  const productOptions = useMemo(() => {
    return productCodes.map((pc) => ({
      value: String(pc.id),
      label: `${pc.code} - ${pc.description}`,
    }));
  }, [productCodes]);

  const suggestedProductCodes = useMemo(() => {
    if (!selectedRequest) return [];

    const sourceLabelText = selectedRequest.source_label || "";
    const suggestedNameText = selectedRequest.suggested_name || "";
    const combinedRequestText = `${sourceLabelText} ${suggestedNameText}`.toLowerCase();

    // Stop words to remove from token checks
    const stopWords = new Set(["fee", "charge", "charges", "rate", "rates", "the", "and", "of", "per"]);
    const requestTokens = combinedRequestText
      .split(/[^a-z0-9]+/i)
      .filter((t) => t.length > 0 && !stopWords.has(t));

    const candidates = productCodes.map((pc) => {
      let score = 0;

      // Same domain constraint
      const pcDomain = (pc.domain || "").toUpperCase();
      const targetDomain = newDomain.toUpperCase();
      if (pcDomain === targetDomain) {
        score += 50;
      } else {
        score -= 200;
      }

      // Same category/bucket
      const pcCategory = (pc.category || "").toUpperCase();
      const targetCategory = newCategory.toUpperCase();
      if (pcCategory === targetCategory) {
        score += 15;
      }

      // Same default unit
      const pcUnit = (pc.default_unit || "").toUpperCase();
      const targetUnit = newDefaultUnit.toUpperCase();
      if (pcUnit === targetUnit) {
        score += 10;
      }

      // Token matching
      const pcCodeText = (pc.code || "").toLowerCase();
      const pcDescText = (pc.description || "").toLowerCase();
      const pcCodeTokens = pcCodeText.split(/[^a-z0-9]+/i).filter(Boolean);
      const pcDescTokens = pcDescText.split(/[^a-z0-9]+/i).filter(Boolean);
      const pcAllTokens = new Set([...pcCodeTokens, ...pcDescTokens]);

      let tokenMatches = 0;
      requestTokens.forEach((token) => {
        if (pcAllTokens.has(token)) {
          tokenMatches++;
        }
      });
      score += tokenMatches * 20;

      // Substring matching
      const lowerSuggested = suggestedNameText.toLowerCase();
      const lowerSource = sourceLabelText.toLowerCase();
      if (lowerSuggested && (pcCodeText.includes(lowerSuggested) || pcDescText.includes(lowerSuggested))) {
        score += 30;
      }
      if (lowerSource && (pcCodeText.includes(lowerSource) || pcDescText.includes(lowerSource))) {
        score += 30;
      }

      return {
        productCode: pc,
        score,
      };
    });

    return candidates
      .filter((c) => c.score >= 60)
      .sort((a, b) => b.score - a.score)
      .map((c) => c.productCode)
      .slice(0, 5);
  }, [selectedRequest, productCodes, newDomain, newCategory, newDefaultUnit]);

  const handleOpenApprove = (req: ProductCodeRequestResponse) => {
    setSelectedRequest(req);
    setSelectedProductCodeId("");
    setActionError(null);
    setActionSuccess(null);
    setApproveMode("LINK");

    // Prefill heuristics
    const nameToUse = req.suggested_name || req.source_label || "";
    setNewDescription(nameToUse);

    let resolvedDomain = "EXPORT";
    const lowerName = nameToUse.toLowerCase();
    if (lowerName.includes("import") || lowerName.includes("imp")) {
      resolvedDomain = "IMPORT";
    } else if (lowerName.includes("domestic") || lowerName.includes("dom")) {
      resolvedDomain = "DOMESTIC";
    }
    setNewDomain(resolvedDomain);

    const cleanCode = nameToUse
      .toUpperCase()
      .replace(/[^A-Z0-9\s-]/g, "")
      .trim()
      .replace(/[\s_]+/g, "-");
    
    const prefix = resolvedDomain === "EXPORT" ? "EXP-" : resolvedDomain === "IMPORT" ? "IMP-" : "DOM-";
    const finalCode = cleanCode.startsWith(prefix) ? cleanCode : `${prefix}${cleanCode}`;
    setNewCode(finalCode.substring(0, 30));

    let resolvedCategory = "HANDLING";
    const bucket = (req.suggested_bucket || "").toUpperCase();
    if (bucket.includes("FREIGHT")) resolvedCategory = "FREIGHT";
    else if (bucket.includes("CLEARANCE") || bucket.includes("CUSTOMS")) resolvedCategory = "CLEARANCE";
    else if (bucket.includes("DOC") || bucket.includes("PAPER")) resolvedCategory = "DOCUMENTATION";
    else if (bucket.includes("REGULATORY") || bucket.includes("PERMIT")) resolvedCategory = "REGULATORY";
    else if (bucket.includes("CARTAGE") || bucket.includes("PICKUP") || bucket.includes("DELIVERY")) resolvedCategory = "CARTAGE";
    else if (bucket.includes("AGENCY")) resolvedCategory = "AGENCY";
    else if (bucket.includes("SCREENING") || bucket.includes("SECURITY")) resolvedCategory = "SCREENING";
    else if (bucket.includes("SURCHARGE")) resolvedCategory = "SURCHARGE";
    setNewCategory(resolvedCategory);

    let resolvedUnit = "SHIPMENT";
    const basis = (req.suggested_basis || "").toLowerCase();
    if (basis.includes("kg") || basis.includes("kilogram")) resolvedUnit = "KG";
    else if (basis.includes("percent")) resolvedUnit = "PERCENT";
    setNewDefaultUnit(resolvedUnit);

    setNewIsGstApplicable(resolvedDomain !== "EXPORT");
    setNewGstTreatment(resolvedDomain === "EXPORT" ? "ZERO_RATED" : "STANDARD");

    setNewGlRevenueCode("REVENUE-PENDING");
    setNewGlCostCode("COST-PENDING");

    setApproveOpen(true);
    void loadProductCodes();
  };

  const handleOpenReject = (req: ProductCodeRequestResponse) => {
    setSelectedRequest(req);
    setRejectionReason("");
    setActionError(null);
    setActionSuccess(null);
    setRejectOpen(true);
  };

  const handleApproveConfirm = async () => {
    if (!selectedRequest) return;
    setSubmittingAction(true);
    setActionError(null);

    let payload: { product_code_id?: number; create_product_code_data?: Record<string, unknown> } = {};
    if (approveMode === "LINK") {
      if (!selectedProductCodeId) {
        setActionError("Please select a ProductCode to link.");
        setSubmittingAction(false);
        return;
      }
      payload = { product_code_id: Number(selectedProductCodeId) };
    } else {
      const pcId = Number(newId);
      if (isNaN(pcId) || pcId <= 0) {
        setActionError("Please enter a valid numeric ProductCode ID.");
        setSubmittingAction(false);
        return;
      }

      const normalizedCode = newCode.trim().toUpperCase();
      if (!normalizedCode) {
        setActionError("Please enter a ProductCode code.");
        setSubmittingAction(false);
        return;
      }

      payload = {
        create_product_code_data: {
          id: pcId,
          code: normalizedCode,
          description: newDescription,
          domain: newDomain,
          category: newCategory,
          is_gst_applicable: newIsGstApplicable,
          gst_treatment: newGstTreatment,
          gl_revenue_code: newGlRevenueCode,
          gl_cost_code: newGstTreatment === "EXEMPT" ? "" : newGlCostCode,
          default_unit: newDefaultUnit,
        }
      };
    }

    try {
      await approveProductCodeRequest(selectedRequest.id, payload);
      setActionSuccess("Request approved and ProductCode associated successfully.");
      setApproveOpen(false);
      void fetchRequests();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to approve request.");
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleRejectConfirm = async () => {
    if (!selectedRequest || !rejectionReason.trim()) return;
    setSubmittingAction(true);
    setActionError(null);
    try {
      await rejectProductCodeRequest(selectedRequest.id, rejectionReason.trim());
      setActionSuccess("Request rejected successfully.");
      setRejectOpen(false);
      void fetchRequests();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject request.");
    } finally {
      setSubmittingAction(false);
    }
  };

  if (!isAdmin) {
    return (
      <StandardPageContainer>
        <PageHeader
          title="Access Denied"
          description="This page is only available to administrators."
        />
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="px-6 py-5 text-sm text-muted-foreground">
            You do not have permission to view the ProductCode Governance Queue. If you require access, please contact your system administrator.
          </CardContent>
        </Card>
      </StandardPageContainer>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PENDING":
        return <Badge className="bg-amber-100 text-amber-800 border-amber-200">Pending</Badge>;
      case "APPROVED":
        return <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">Approved</Badge>;
      case "REJECTED":
        return <Badge className="bg-rose-100 text-rose-800 border-rose-200">Rejected</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  return (
    <StandardPageContainer>
      <div className="mb-4">
        <Button variant="ghost" asChild className="pl-0 text-slate-500 hover:text-slate-900">
          <Link href="/settings">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Settings
          </Link>
        </Button>
      </div>

      <PageHeader
        title="ProductCode Governance Queue"
        description="Review, verify, and approve or reject custom ProductCode creation requests submitted by the operations team."
      />

      <div className="space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex gap-2 bg-slate-100 p-1 rounded-lg w-fit">
            {(["PENDING", "APPROVED", "REJECTED", "ALL"] as const).map((filter) => (
              <Button
                key={filter}
                variant={statusFilter === filter ? "default" : "ghost"}
                size="sm"
                onClick={() => setStatusFilter(filter)}
                className="text-xs"
              >
                {filter === "ALL" ? "All Requests" : filter}
              </Button>
            ))}
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {actionSuccess && (
          <Alert className="border-emerald-200 bg-emerald-50 text-emerald-900">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            <AlertDescription>{actionSuccess}</AlertDescription>
          </Alert>
        )}

        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4 text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm font-medium">Fetching request queue...</p>
          </div>
        ) : requests.length === 0 ? (
          <Card className="border-slate-200 shadow-sm border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-16 gap-3 text-slate-500 text-center">
              <Database className="h-10 w-10 text-slate-400" />
              <div className="space-y-1">
                <p className="font-semibold text-slate-900">Queue is empty</p>
                <p className="text-sm text-slate-500">
                  No requests matching status <span className="font-semibold">{statusFilter}</span> were found.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
            <Table>
              <TableHeader className="bg-slate-50/75">
                <TableRow>
                  <TableHead className="w-[180px] font-semibold text-slate-700">Source Label</TableHead>
                  <TableHead className="w-[180px] font-semibold text-slate-700">Suggested Name</TableHead>
                  <TableHead className="w-[120px] font-semibold text-slate-700">Bucket</TableHead>
                  <TableHead className="w-[120px] font-semibold text-slate-700">Basis</TableHead>
                  <TableHead className="font-semibold text-slate-700">Reason / Context</TableHead>
                  <TableHead className="w-[130px] font-semibold text-slate-700">Requested By</TableHead>
                  <TableHead className="w-[140px] font-semibold text-slate-700">Date Created</TableHead>
                  <TableHead className="w-[100px] font-semibold text-slate-700">Status</TableHead>
                  <TableHead className="w-[160px] text-right font-semibold text-slate-700">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requests.map((req) => (
                  <TableRow key={req.id} className="hover:bg-slate-50/50">
                    <TableCell className="font-medium text-slate-900">{req.source_label}</TableCell>
                    <TableCell className="text-slate-800">{req.suggested_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] uppercase font-semibold text-slate-600 bg-slate-50">
                        {req.suggested_bucket}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] uppercase font-semibold text-slate-600 bg-slate-50">
                        {req.suggested_basis}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-slate-600 max-w-[240px] truncate" title={req.suggested_reason}>
                      {req.suggested_reason}
                    </TableCell>
                    <TableCell className="text-slate-600 text-xs">{req.created_by_username}</TableCell>
                    <TableCell className="text-slate-600 text-xs">
                      {new Date(req.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>{getStatusBadge(req.status)}</TableCell>
                    <TableCell className="text-right">
                      {req.status === "PENDING" ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 border-rose-200 text-rose-700 hover:bg-rose-50 hover:text-rose-800 hover:border-rose-300"
                            onClick={() => handleOpenReject(req)}
                          >
                            Reject
                          </Button>
                          <Button
                            size="sm"
                            className="h-8 bg-emerald-600 hover:bg-emerald-700 text-white"
                            onClick={() => handleOpenApprove(req)}
                          >
                            Approve
                          </Button>
                        </div>
                      ) : (
                        <div className="text-xs text-slate-500 italic pr-2">
                          {req.status === "APPROVED" && req.approved_product_code ? (
                            <span className="flex items-center justify-end gap-1 font-medium text-slate-600">
                              Linked to PC {req.approved_product_code}
                            </span>
                          ) : req.status === "REJECTED" ? (
                            <span className="text-slate-400" title={req.rejection_reason || ""}>
                              Rejected
                            </span>
                          ) : (
                            "—"
                          )}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Approval Dialog */}
      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent className="sm:max-w-lg bg-white">
          <DialogHeader>
            <DialogTitle>Approve & Associate ProductCode</DialogTitle>
            <DialogDescription>
              Resolve request &quot;{selectedRequest?.suggested_name}&quot; by linking to an existing code or creating a new one inline.
            </DialogDescription>
          </DialogHeader>

          {actionError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{actionError}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-4 py-2">
            <div className="grid gap-1.5">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Request Details</span>
              <div className="rounded-lg bg-slate-50 p-3 text-sm space-y-1 border border-slate-100 grid grid-cols-3 gap-2">
                <div><span className="font-semibold text-slate-700 block text-xs">Source label:</span> {selectedRequest?.source_label}</div>
                <div><span className="font-semibold text-slate-700 block text-xs">Suggested bucket:</span> {selectedRequest?.suggested_bucket}</div>
                <div><span className="font-semibold text-slate-700 block text-xs">Suggested basis:</span> {selectedRequest?.suggested_basis}</div>
              </div>
            </div>

            {/* Approval Mode Toggle Tabs */}
            <div className="flex border-b border-slate-150">
              <button
                type="button"
                onClick={() => setApproveMode("LINK")}
                className={`flex-1 pb-2 text-sm font-semibold border-b-2 text-center transition-colors ${
                  approveMode === "LINK"
                    ? "border-emerald-600 text-emerald-700"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Link Existing Code
              </button>
              <button
                type="button"
                onClick={() => setApproveMode("CREATE")}
                className={`flex-1 pb-2 text-sm font-semibold border-b-2 text-center transition-colors ${
                  approveMode === "CREATE"
                    ? "border-emerald-600 text-emerald-700"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                Create New Code
              </button>
            </div>

            {approveMode === "LINK" ? (
              <div className="grid gap-2 pt-2">
                <Label htmlFor="pc-combobox" className="text-xs font-semibold text-slate-600">Select Canonical ProductCode</Label>
                <Combobox
                  options={productOptions}
                  value={selectedProductCodeId}
                  onChange={setSelectedProductCodeId}
                  placeholder={loadingProductCodes ? "Loading product codes..." : "Search catalogue codes..."}
                  emptyMessage={loadingProductCodes ? "Loading catalogue..." : "No product codes found."}
                  disabled={loadingProductCodes || submittingAction}
                />
              </div>
            ) : (
              <div className="space-y-3 max-h-[350px] overflow-y-auto pr-1 pt-2">
                {suggestedProductCodes.length > 0 && (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-3.5 space-y-2">
                    <div className="space-y-1">
                      <h4 className="text-xs font-semibold text-emerald-950 flex items-center gap-1.5">
                        <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                        Possible existing ProductCodes found
                      </h4>
                      <p className="text-[11px] text-emerald-800 leading-normal">
                        Review these before creating a new ProductCode. Multiple source charges can use the same ProductCode. Create a new ProductCode only if this is genuinely a different charge category.
                      </p>
                    </div>
                    <div className="space-y-1.5 max-h-[160px] overflow-y-auto pr-1">
                      {suggestedProductCodes.map((pc) => (
                        <div key={pc.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-lg border border-emerald-100 bg-white p-2 shadow-sm">
                          <div className="space-y-0.5">
                            <div className="text-xs font-mono font-bold text-slate-900">{pc.code}</div>
                            <div className="text-[11px] text-slate-600 leading-tight">{pc.description}</div>
                            <div className="flex flex-wrap gap-1 pt-0.5">
                              <Badge variant="outline" className="text-[8px] px-1 py-0 uppercase bg-slate-50 text-slate-500 font-semibold border-slate-200">
                                {pc.domain}
                              </Badge>
                              <Badge variant="outline" className="text-[8px] px-1 py-0 uppercase bg-slate-50 text-slate-500 font-semibold border-slate-200">
                                {pc.category}
                              </Badge>
                              {pc.default_unit && (
                                <Badge variant="outline" className="text-[8px] px-1 py-0 uppercase bg-slate-50 text-slate-500 font-semibold border-slate-200">
                                  {pc.default_unit}
                                </Badge>
                              )}
                            </div>
                          </div>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="h-7 text-[10px] px-2.5 border-emerald-200 text-emerald-700 hover:bg-emerald-50 hover:text-emerald-800 self-end sm:self-center"
                            onClick={() => {
                              setSelectedProductCodeId(String(pc.id));
                              setApproveMode("LINK");
                            }}
                          >
                            Use this existing ProductCode
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="new-domain" className="text-xs font-semibold text-slate-600">Domain</Label>
                    <select
                      id="new-domain"
                      value={newDomain}
                      onChange={(e) => setNewDomain(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                      disabled={submittingAction}
                    >
                      <option value="EXPORT">Export (1xxx)</option>
                      <option value="IMPORT">Import (2xxx)</option>
                      <option value="DOMESTIC">Domestic (3xxx)</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="new-id" className="text-xs font-semibold text-slate-600">ProductCode ID</Label>
                    <Input
                      id="new-id"
                      type="number"
                      value={newId}
                      onChange={(e) => setNewId(e.target.value)}
                      placeholder="e.g. 1005"
                      disabled={submittingAction}
                    />
                    <span className="text-[10px] text-slate-400 block mt-0.5">Suggested only. Final validation happens on save.</span>
                  </div>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="new-code" className="text-xs font-semibold text-slate-600">Code</Label>
                  <Input
                    id="new-code"
                    type="text"
                    value={newCode}
                    onChange={(e) => setNewCode(e.target.value)}
                    placeholder="e.g. EXP-FUEL-SUR"
                    disabled={submittingAction}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="new-description" className="text-xs font-semibold text-slate-600">Description</Label>
                  <Input
                    id="new-description"
                    type="text"
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="e.g. Export Fuel Surcharge"
                    disabled={submittingAction}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="new-category" className="text-xs font-semibold text-slate-600">Category</Label>
                    <select
                      id="new-category"
                      value={newCategory}
                      onChange={(e) => setNewCategory(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                      disabled={submittingAction}
                    >
                      <option value="FREIGHT">Freight</option>
                      <option value="HANDLING">Handling & Terminal</option>
                      <option value="CLEARANCE">Customs Clearance</option>
                      <option value="DOCUMENTATION">Documentation</option>
                      <option value="REGULATORY">Regulatory / Permit</option>
                      <option value="CARTAGE">Pickup & Delivery</option>
                      <option value="AGENCY">Agency Fees</option>
                      <option value="SCREENING">Security & Screening</option>
                      <option value="SURCHARGE">Surcharges</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="new-unit" className="text-xs font-semibold text-slate-600">Default Unit</Label>
                    <select
                      id="new-unit"
                      value={newDefaultUnit}
                      onChange={(e) => setNewDefaultUnit(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                      disabled={submittingAction}
                    >
                      <option value="SHIPMENT">Per Shipment</option>
                      <option value="KG">Per Kilogram</option>
                      <option value="PERCENT">Percentage</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="new-gst-treatment" className="text-xs font-semibold text-slate-600">GST Treatment</Label>
                    <select
                      id="new-gst-treatment"
                      value={newGstTreatment}
                      onChange={(e) => setNewGstTreatment(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                      disabled={submittingAction}
                    >
                      <option value="STANDARD">Standard (10% GST)</option>
                      <option value="ZERO_RATED">Zero-Rated (Export)</option>
                      <option value="EXEMPT">Exempt (Disbursement)</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between pt-6 px-1">
                    <Label htmlFor="new-gst-applicable" className="text-xs font-semibold text-slate-600 cursor-pointer">GST Applicable</Label>
                    <Switch
                      id="new-gst-applicable"
                      checked={newIsGstApplicable}
                      onCheckedChange={setNewIsGstApplicable}
                      disabled={submittingAction}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="new-revenue-code" className="text-xs font-semibold text-slate-600">GL Revenue Code</Label>
                    <Input
                      id="new-revenue-code"
                      type="text"
                      value={newGlRevenueCode}
                      onChange={(e) => setNewGlRevenueCode(e.target.value)}
                      placeholder="e.g. 4000"
                      disabled={submittingAction}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="new-cost-code" className="text-xs font-semibold text-slate-600">GL Cost Code</Label>
                    <Input
                      id="new-cost-code"
                      type="text"
                      value={newGlCostCode}
                      onChange={(e) => setNewGlCostCode(e.target.value)}
                      placeholder="e.g. 5000"
                      disabled={newGstTreatment === "EXEMPT" || submittingAction}
                    />
                  </div>
                  <span className="text-[10px] text-slate-400 block mt-1 col-span-2">Temporary RateEngine placeholder. Finance can replace this later if required.</span>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setApproveOpen(false)}
              disabled={submittingAction}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleApproveConfirm}
              disabled={
                approveMode === "LINK"
                  ? !selectedProductCodeId || submittingAction
                  : !newId || !newCode || !newDescription || submittingAction
              }
              loading={submittingAction}
              loadingText="Saving..."
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              Confirm Approval
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rejection Dialog */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent className="sm:max-w-md bg-white">
          <DialogHeader>
            <DialogTitle>Reject ProductCode Request</DialogTitle>
            <DialogDescription>
              Provide context for rejecting request &quot;{selectedRequest?.suggested_name}&quot;.
            </DialogDescription>
          </DialogHeader>

          {actionError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{actionError}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="rejection-reason-input" className="text-xs font-semibold text-slate-600">Rejection Reason</Label>
              <Textarea
                id="rejection-reason-input"
                placeholder="e.g. Code matches existing POM terminal charge..."
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                disabled={submittingAction}
                className="min-h-[100px]"
              />
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setRejectOpen(false)}
              disabled={submittingAction}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleRejectConfirm}
              disabled={!rejectionReason.trim() || submittingAction}
              loading={submittingAction}
              loadingText="Rejecting..."
              variant="destructive"
            >
              Confirm Rejection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </StandardPageContainer>
  );
}
