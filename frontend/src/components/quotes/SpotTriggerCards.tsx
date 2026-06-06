import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import type { V3QuoteComputeResponse } from "@/lib/types";

export interface SpotWorkflowRequiredCardProps {
  quote: V3QuoteComputeResponse;
  spotLaunching: boolean;
  spotLaunchError: string | null;
  onLaunchSpot: () => void | Promise<void>;
  onReturnToEdit: () => void;
}

export function SpotWorkflowRequiredCard({
  quote,
  spotLaunching,
  spotLaunchError,
  onLaunchSpot,
  onReturnToEdit,
}: SpotWorkflowRequiredCardProps) {
  return (
    <Card className="border-amber-200 bg-amber-50/40">
      <CardHeader>
        <CardTitle className="text-lg text-amber-800">SPOT Workflow Required</CardTitle>
        <CardDescription>
          This quote is incomplete and is not linked to an active SPOT envelope yet.
          Launch the current SPOT workflow from here, or return to edit if you need to refresh the quote inputs.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="text-sm text-muted-foreground">Quote: {quote.quote_number}</div>
          {spotLaunchError ? (
            <div className="text-sm text-destructive">{spotLaunchError}</div>
          ) : (
            <div className="text-sm text-muted-foreground">
              The detail view will evaluate the latest SPOT trigger and open the live workflow if it is still required.
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onReturnToEdit}>
            Return To Quote Edit
          </Button>
          <Button onClick={onLaunchSpot} disabled={spotLaunching}>
            {spotLaunching ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Opening SPOT...
              </>
            ) : (
              "Open SPOT Workflow"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export interface SpotTriggerCheckingCardProps {
  quote: V3QuoteComputeResponse;
}

export function SpotTriggerCheckingCard({
  quote,
}: SpotTriggerCheckingCardProps) {
  return (
    <Card className="border-slate-200 bg-slate-50/60">
      <CardHeader>
        <CardTitle className="text-lg text-slate-900">Checking Quote Completion</CardTitle>
        <CardDescription>
          This quote is currently marked incomplete. Verifying the latest SPOT trigger before deciding whether the SPOT workflow is still required.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-3 text-sm text-slate-600">
        <Loader2 className="h-4 w-4 animate-spin" />
        Re-checking {quote.quote_number} against the latest SPOT trigger...
      </CardContent>
    </Card>
  );
}

export interface IncompleteQuoteCardProps {
  quote: V3QuoteComputeResponse;
  triggerCheckError: string | null;
  onRetryCheck: () => void | Promise<void>;
  onReturnToEdit: () => void;
}

export function IncompleteQuoteCard({
  quote,
  triggerCheckError,
  onRetryCheck,
  onReturnToEdit,
}: IncompleteQuoteCardProps) {
  return (
    <Card className="border-slate-200 bg-slate-50/60">
      <CardHeader>
        <CardTitle className="text-lg text-slate-900">Incomplete Quote</CardTitle>
        <CardDescription>
          The latest SPOT trigger check does not require the SPOT workflow for this quote. The quote is still incomplete, so return to edit and refresh the missing rate inputs.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="text-sm text-muted-foreground">Quote: {quote.quote_number}</div>
          {triggerCheckError ? (
            <div className="text-sm text-destructive">
              Unable to verify the latest SPOT trigger automatically: {triggerCheckError}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              Return to the quote editor to refresh pricing coverage instead of launching SPOT.
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {triggerCheckError ? (
            <Button variant="outline" onClick={onRetryCheck}>
              Retry Trigger Check
            </Button>
          ) : null}
          <Button variant="outline" onClick={onReturnToEdit}>
            Return To Quote Edit
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
