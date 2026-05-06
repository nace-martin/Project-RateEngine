'use client';

import { FormEvent, useEffect, useState } from 'react';

import CompanySearchCombobox from '@/components/CompanySearchCombobox';
import { createTask, listOpportunitiesByCompany, updateTask, type TaskPayload } from '@/lib/api/crm';
import type { CompanySearchResult, Opportunity, Task } from '@/lib/types';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/context/toast-context';

type TaskDialogDefaults = {
  company?: CompanySearchResult | null;
  opportunity?: Opportunity | null;
  description?: string;
  dueDate?: string;
  status?: string;
};

type TaskDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task?: Task | null;
  defaults?: TaskDialogDefaults;
  onSaved?: (task: Task) => void;
};

const formatDateInputValue = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const todayIso = () => formatDateInputValue(new Date());
const noOpportunityValue = 'none';

export function nextBusinessDay(from = new Date()): string {
  const date = new Date(from);
  date.setDate(date.getDate() + 1);
  const day = date.getDay();
  if (day === 6) date.setDate(date.getDate() + 2);
  if (day === 0) date.setDate(date.getDate() + 1);
  return formatDateInputValue(date);
}

export function TaskDialog({
  open,
  onOpenChange,
  task = null,
  defaults,
  onSaved,
}: TaskDialogProps) {
  const { toast } = useToast();
  const [description, setDescription] = useState('');
  const [dueDate, setDueDate] = useState(todayIso());
  const [selectedCompany, setSelectedCompany] = useState<CompanySearchResult | null>(null);
  const [opportunityId, setOpportunityId] = useState('');
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [opportunitiesLoading, setOpportunitiesLoading] = useState(false);
  const [opportunitiesError, setOpportunitiesError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const isEditing = Boolean(task);
  const defaultCompanyId = defaults?.company?.id;
  const defaultCompanyName = defaults?.company?.name;
  const defaultOpportunityId = defaults?.opportunity?.id;
  const defaultOpportunityTitle = defaults?.opportunity?.title;
  const defaultOpportunityCompanyId = defaults?.opportunity?.company;
  const defaultOpportunityCompanyName = defaults?.opportunity?.company_name;
  const allowContextSelection = !isEditing && !defaultCompanyId && !defaultOpportunityId;

  useEffect(() => {
    if (!open) return;
    const defaultCompany = defaultCompanyId && defaultCompanyName
      ? {
        id: defaultCompanyId,
        name: defaultCompanyName,
      }
      : null;
    const defaultOpportunityCompany = defaultOpportunityCompanyId
      ? {
        id: defaultOpportunityCompanyId,
        name: defaultOpportunityCompanyName || 'Selected company',
      }
      : null;
    setDescription(task?.description || defaults?.description || '');
    setDueDate(task?.due_date || defaults?.dueDate || nextBusinessDay());
    setSelectedCompany(defaultCompany || defaultOpportunityCompany);
    setOpportunityId(defaultOpportunityId || task?.opportunity || '');
    setOpportunitiesError(null);
  }, [
    defaults?.description,
    defaults?.dueDate,
    defaultCompanyId,
    defaultCompanyName,
    defaultOpportunityCompanyId,
    defaultOpportunityCompanyName,
    defaultOpportunityId,
    open,
    task,
  ]);

  useEffect(() => {
    if (!open || !allowContextSelection || !selectedCompany?.id) {
      setOpportunities([]);
      setOpportunitiesLoading(false);
      setOpportunitiesError(null);
      return;
    }

    let isActive = true;
    setOpportunitiesLoading(true);
    setOpportunitiesError(null);

    listOpportunitiesByCompany(selectedCompany.id)
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
  }, [allowContextSelection, open, opportunityId, selectedCompany?.id]);

  const companyName = defaultCompanyName;
  const opportunityTitle = defaultOpportunityTitle;
  const ownerName = task?.owner_username || (task?.owner ? `Owner #${task.owner}` : null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;
    if (!description.trim() || !dueDate) {
      toast({
        title: 'Task needs required fields',
        description: 'Description and due date are required.',
        variant: 'destructive',
      });
      return;
    }

    const payloadCompany = allowContextSelection
      ? selectedCompany?.id || null
      : defaultCompanyId || task?.company || null;
    const payloadOpportunity = allowContextSelection
      ? opportunityId || null
      : defaultOpportunityId || task?.opportunity || null;

    if (!payloadCompany && !payloadOpportunity) {
      toast({
        title: 'Task context is required',
        description: 'Select a company before creating this task. Opportunity is optional.',
        variant: 'destructive',
      });
      return;
    }

    const payload: TaskPayload = {
      company: payloadCompany,
      opportunity: payloadOpportunity,
      description: description.trim(),
      due_date: dueDate,
      status: task?.status || defaults?.status || 'PENDING',
    };

    setSaving(true);
    try {
      const saved = isEditing && task
        ? await updateTask(task.id, payload)
        : await createTask(payload);
      toast({ title: isEditing ? 'Task Updated' : 'Task Created', variant: 'success' });
      onSaved?.(saved);
      onOpenChange(false);
    } catch (error) {
      toast({
        title: isEditing ? 'Task Update Failed' : 'Task Create Failed',
        description: error instanceof Error ? error.message : 'The task was not saved.',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !saving && onOpenChange(nextOpen)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Task' : 'Create Task'}</DialogTitle>
          <DialogDescription>
            Capture a clear follow-up task. Required fields are description and due date.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          {allowContextSelection ? (
            <div className="space-y-4 rounded-md border border-slate-200 bg-slate-50 p-3">
              <CompanySearchCombobox
                label="Company"
                name="crm-task-company"
                value={selectedCompany}
                onSelect={(company) => {
                  setSelectedCompany(company);
                  setOpportunityId('');
                }}
                placeholder="Search customers"
                helperText="Required unless an opportunity is linked. Opportunity remains optional."
                disabled={saving}
              />
              <div className="space-y-2">
                <Label htmlFor="crm-task-opportunity">Opportunity</Label>
                <Select
                  value={opportunityId || noOpportunityValue}
                  onValueChange={(value) => setOpportunityId(value === noOpportunityValue ? '' : value)}
                  disabled={saving || !selectedCompany || opportunitiesLoading}
                >
                  <SelectTrigger id="crm-task-opportunity">
                    <SelectValue placeholder={selectedCompany ? 'Optional' : 'Select a company first'} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={noOpportunityValue}>No opportunity linked</SelectItem>
                    {opportunities.map((opportunity) => (
                      <SelectItem key={opportunity.id} value={opportunity.id}>
                        {opportunity.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className={`text-xs ${opportunitiesError ? 'text-destructive' : 'text-muted-foreground'}`}>
                  {opportunitiesLoading
                    ? 'Loading opportunities...'
                    : opportunitiesError || (selectedCompany ? 'Only opportunities for the selected company are shown.' : 'Select a company to link an opportunity.')}
                </p>
              </div>
              <p className="text-xs text-muted-foreground">Owner: current user/default</p>
            </div>
          ) : (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <div><span className="font-medium">Company:</span> {companyName || (task?.company ? 'Company linked' : 'No company selected')}</div>
              <div><span className="font-medium">Opportunity:</span> {opportunityTitle || (task?.opportunity ? 'Opportunity linked' : 'No opportunity linked')}</div>
              <div><span className="font-medium">Owner:</span> {ownerName || 'current user/default'}</div>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="crm-task-description">Description</Label>
            <Textarea
              id="crm-task-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              disabled={saving}
              className="min-h-28"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="crm-task-due-date">Due date</Label>
            <Input
              id="crm-task-due-date"
              type="date"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
              disabled={saving}
              required
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} loadingText="Saving" disabled={saving}>
              {isEditing ? 'Save Task' : 'Create Task'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
