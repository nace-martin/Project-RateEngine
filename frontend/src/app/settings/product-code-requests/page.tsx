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

  const productOptions = useMemo(() => {
    return productCodes.map((pc) => ({
      value: String(pc.id),
      label: `${pc.code} - ${pc.description}`,
    }));
  }, [productCodes]);

  const handleOpenApprove = (req: ProductCodeRequestResponse) => {
    setSelectedRequest(req);
    setSelectedProductCodeId("");
    setActionError(null);
    setActionSuccess(null);
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
    if (!selectedRequest || !selectedProductCodeId) return;
    setSubmittingAction(true);
    setActionError(null);
    try {
      await approveProductCodeRequest(selectedRequest.id, Number(selectedProductCodeId));
      setActionSuccess("Request approved and linked successfully.");
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
        <DialogContent className="sm:max-w-md bg-white">
          <DialogHeader>
            <DialogTitle>Approve & Link ProductCode</DialogTitle>
            <DialogDescription>
              Map request &quot;{selectedRequest?.suggested_name}&quot; to a canonical code in the catalogue.
            </DialogDescription>
          </DialogHeader>

          {actionError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{actionError}</AlertDescription>
            </Alert>
          )}

          <div className="space-y-4 py-4">
            <div className="grid gap-1.5">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Request Details</span>
              <div className="rounded-lg bg-slate-50 p-3 text-sm space-y-1 border border-slate-100">
                <div><span className="font-semibold text-slate-700">Source label:</span> {selectedRequest?.source_label}</div>
                <div><span className="font-semibold text-slate-700">Suggested bucket:</span> {selectedRequest?.suggested_bucket}</div>
                <div><span className="font-semibold text-slate-700">Suggested basis:</span> {selectedRequest?.suggested_basis}</div>
              </div>
            </div>

            <div className="grid gap-2">
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
              disabled={!selectedProductCodeId || submittingAction}
              loading={submittingAction}
              loadingText="Linking..."
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              Approve & Link
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
