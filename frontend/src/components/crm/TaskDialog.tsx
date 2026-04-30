'use client';

import { FormEvent, useEffect, useState } from 'react';

import { createTask, updateTask, type TaskPayload } from '@/lib/api/crm';
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
  const [saving, setSaving] = useState(false);
  const isEditing = Boolean(task);

  useEffect(() => {
    if (!open) return;
    setDescription(task?.description || defaults?.description || '');
    setDueDate(task?.due_date || defaults?.dueDate || nextBusinessDay());
  }, [defaults?.description, defaults?.dueDate, open, task]);

  const companyName = defaults?.company?.name;
  const opportunityTitle = defaults?.opportunity?.title;
  const ownerName = task?.owner_username;

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

    const payload: TaskPayload = {
      company: defaults?.company?.id || task?.company || null,
      opportunity: defaults?.opportunity?.id || task?.opportunity || null,
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
          <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
            <div><span className="font-medium">Company:</span> {companyName || (task?.company ? 'Company linked' : 'None')}</div>
            <div><span className="font-medium">Opportunity:</span> {opportunityTitle || (task?.opportunity ? 'Opportunity linked' : 'None')}</div>
            <div><span className="font-medium">Owner:</span> {ownerName || 'Assigned by default'}</div>
          </div>

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
