export type EngagementStatus = 'Active' | 'Due Soon' | 'Overdue' | 'Dormant' | 'Never Contacted';

const DAY_MS = 24 * 60 * 60 * 1000;

export function daysSinceInteraction(value?: string | null, now = new Date()): number | null {
  if (!value) return null;
  const lastInteraction = new Date(value);
  if (Number.isNaN(lastInteraction.getTime())) return null;
  return Math.max(0, Math.floor((now.getTime() - lastInteraction.getTime()) / DAY_MS));
}

export function engagementStatus(value?: string | null, now = new Date()): EngagementStatus {
  const days = daysSinceInteraction(value, now);
  if (days === null) return 'Never Contacted';
  if (days <= 60) return 'Active';
  if (days <= 89) return 'Due Soon';
  if (days <= 179) return 'Overdue';
  return 'Dormant';
}

export function needsFollowUp(value?: string | null, now = new Date()): boolean {
  const days = daysSinceInteraction(value, now);
  return days === null || days >= 90;
}

export function formatEngagementDate(value?: string | null): string {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Never';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
}
