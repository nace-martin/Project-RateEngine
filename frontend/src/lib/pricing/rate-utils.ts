export interface RateWeightBreak {
  min_kg: number;
  rate: string;
}

export function isoDateWithOffset(offsetDays = 0): string {
  const base = new Date();
  base.setDate(base.getDate() + offsetDays);
  return base.toISOString().split('T')[0];
}

export function getRateStatus(rate: { valid_from: string; valid_until: string }): 'ACTIVE' | 'EXPIRED' | 'SCHEDULED' {
  const today = new Date().toISOString().split('T')[0];
  if (rate.valid_until < today) return 'EXPIRED';
  if (rate.valid_from > today) return 'SCHEDULED';
  return 'ACTIVE';
}

export function cleanWeightBreaks(weightBreaks: Array<{ min_kg: string; rate: string }>): RateWeightBreak[] {
  return weightBreaks
    .filter((row) => row.min_kg.trim() !== '' || row.rate.trim() !== '')
    .map((row) => ({
      min_kg: Number(row.min_kg),
      rate: row.rate.trim(),
    }));
}
