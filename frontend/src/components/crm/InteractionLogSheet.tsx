'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import CompanySearchCombobox from '@/components/CompanySearchCombobox';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/context/toast-context';
import { createInteraction, listOpportunitiesByCompany } from '@/lib/api/crm';
import type { CompanySearchResult, CreateInteractionPayload, InteractionType, Opportunity } from '@/lib/types';
import { cn } from '@/lib/utils';

type QuickLogInteractionType = Exclude<InteractionType, 'SYSTEM'>;

const INTERACTION_TYPES: { value: QuickLogInteractionType; label: string }[] = [
  { value: 'CALL', label: 'Call' },
  { value: 'MEETING', label: 'Meeting' },
  { value: 'EMAIL', label: 'Email' },
  { value: 'SITE_VISIT', label: 'Site Visit' },
];

type InteractionLogSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  prefilledCompany?: CompanySearchResult | null;
  prefilledOpportunity?: Opportunity | null;
};

const emptyOpportunityValue = 'none';

export function InteractionLogSheet({
  open,
  onOpenChange,
  prefilledCompany = null,
  prefilledOpportunity = null,
}: InteractionLogSheetProps) {
  const { toast } = useToast();
  const [company, setCompany] = useState<CompanySearchResult | null>(prefilledCompany);
  const [interactionType, setInteractionType] = useState<QuickLogInteractionType | ''>('');
  const [summary, setSummary] = useState('');
  const [opportunityId, setOpportunityId] = useState<string>('');
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [opportunitiesLoading, setOpportunitiesLoading] = useState(false);
  const [opportunitiesError, setOpportunitiesError] = useState<string | null>(null);
  const [showNextAction, setShowNextAction] = useState(false);
  const [nextAction, setNextAction] = useState('');
  const [nextActionDate, setNextActionDate] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (prefilledCompany) {
      setCompany(prefilledCompany);
    }
  }, [open, prefilledCompany]);

  useEffect(() => {
    if (!open || !prefilledOpportunity) return;
    const companyRef = prefilledOpportunity.company
      ? {
        id: prefilledOpportunity.company,
        name: prefilledOpportunity.company_name || 'Selected company',
      }
      : prefilledCompany;
    if (companyRef) {
      setCompany(companyRef);
    }
    setOpportunityId(prefilledOpportunity.id);
  }, [open, prefilledCompany, prefilledOpportunity]);

  useEffect(() => {
    if (!company?.id) {
      setOpportunities([]);
      setOpportunityId('');
      setOpportunitiesError(null);
      return;
    }

    let isActive = true;
    setOpportunitiesLoading(true);
    setOpportunitiesError(null);

    listOpportunitiesByCompany(company.id)
      .then((items) => {
        if (!isActive) return;
        setOpportunities(items);
        if (opportunityId && !items.some((item) => item.id === opportunityId)) {
          setOpportunityId('');
        }
      })
      .catch((error: Error) => {
        if (!isActive) return;
        setOpportunities([]);
        setOpportunitiesError(error.message || 'Unable to load opportunities.');
      })
      .finally(() => {
        if (isActive) {
          setOpportunitiesLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [company?.id, opportunityId]);

  const selectedOpportunity = useMemo(
    () => opportunities.find((item) => item.id === opportunityId) || null,
    [opportunities, opportunityId],
  );

  const resetForm = () => {
    setCompany(prefilledCompany);
    setInteractionType('');
    setSummary('');
    setOpportunityId(prefilledOpportunity?.id || '');
    setShowNextAction(false);
    setNextAction('');
    setNextActionDate('');
    setOpportunitiesError(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;

    if (!company) {
      toast({
        title: 'Company is required',
        description: 'Select a company before saving the activity.',
        variant: 'destructive',
      });
      return;
    }
    if (!interactionType) {
      toast({
        title: 'Interaction type is required',
        description: 'Choose call, meeting, email, or site visit.',
        variant: 'destructive',
      });
      return;
    }
    if (!summary.trim()) {
      toast({
        title: 'Summary is required',
        description: 'Add a short activity note before saving.',
        variant: 'destructive',
      });
      return;
    }

    const payload: CreateInteractionPayload = {
      company: company.id,
      interaction_type: interactionType,
      summary: summary.trim(),
      opportunity: opportunityId || null,
      next_action: showNextAction ? nextAction.trim() : '',
      next_action_date: showNextAction && nextActionDate ? nextActionDate : null,
    };

    setSaving(true);
    try {
      await createInteraction(payload);
      toast({
        title: 'Activity logged',
        description: selectedOpportunity
          ? `Saved against ${selectedOpportunity.title}.`
          : `Saved against ${company.name}.`,
        variant: 'success',
      });
      resetForm();
      onOpenChange(false);
    } catch (error) {
      toast({
        title: 'Could not log activity',
        description: error instanceof Error ? error.message : 'The activity was not saved.',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex h-full w-full flex-col overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Log Activity</SheetTitle>
        </SheetHeader>

        <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-5 pt-4">
          <CompanySearchCombobox
            label="Company"
            name="crm-company"
            value={company}
            onSelect={(selected) => {
              setCompany(selected);
              setOpportunityId('');
            }}
            placeholder="Search customers"
            disabled={saving}
          />

          <div className="space-y-2">
            <Label htmlFor="crm-interaction-type">Interaction type</Label>
            <Select
              value={interactionType}
              onValueChange={(value) => setInteractionType(value as QuickLogInteractionType)}
              disabled={saving}
            >
              <SelectTrigger id="crm-interaction-type">
                <SelectValue placeholder="Select activity type" />
              </SelectTrigger>
              <SelectContent>
                {INTERACTION_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="crm-summary">Summary notes</Label>
            <Textarea
              id="crm-summary"
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="What happened?"
              disabled={saving}
              className="min-h-32"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="crm-opportunity">Linked opportunity</Label>
            <Select
              value={opportunityId || emptyOpportunityValue}
              onValueChange={(value) => setOpportunityId(value === emptyOpportunityValue ? '' : value)}
              disabled={saving || !company || opportunitiesLoading}
            >
              <SelectTrigger id="crm-opportunity">
                <SelectValue placeholder={company ? 'Optional' : 'Select a company first'} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={emptyOpportunityValue}>No linked opportunity</SelectItem>
                {opportunities.map((opportunity) => (
                  <SelectItem key={opportunity.id} value={opportunity.id}>
                    {opportunity.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className={cn('text-xs text-muted-foreground', opportunitiesError && 'text-destructive')}>
              {opportunitiesLoading
                ? 'Loading opportunities...'
                : opportunitiesError || (company ? 'Only opportunities for the selected company are shown.' : 'Company is required before linking an opportunity.')}
            </p>
          </div>

          <div className="rounded-md border bg-muted/20">
            <button
              type="button"
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-foreground"
              onClick={() => setShowNextAction((value) => !value)}
              disabled={saving}
            >
              <span>Add next action</span>
              <span className="text-xs text-muted-foreground">{showNextAction ? 'Hide' : 'Show'}</span>
            </button>
            {showNextAction ? (
              <div className="space-y-4 border-t p-3">
                <div className="space-y-2">
                  <Label htmlFor="crm-next-action">Next action</Label>
                  <Input
                    id="crm-next-action"
                    value={nextAction}
                    onChange={(event) => setNextAction(event.target.value)}
                    placeholder="Follow up with customer"
                    disabled={saving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="crm-next-action-date">Due date</Label>
                  <Input
                    id="crm-next-action-date"
                    type="date"
                    value={nextActionDate}
                    onChange={(event) => setNextActionDate(event.target.value)}
                    disabled={saving}
                  />
                </div>
              </div>
            ) : null}
          </div>

          <SheetFooter className="mt-auto border-t pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} loadingText="Saving" disabled={saving}>
              Save activity
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
