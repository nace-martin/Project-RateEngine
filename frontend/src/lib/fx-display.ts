export interface FxDisplayRateInput {
    currency: string;
    tt_buy: string | number;
    tt_sell: string | number;
}

export interface FxDisplayRow {
    label: 'TT Buy' | 'TT Sell';
    direction: string;
    from: string;
    to: string;
    value: number;
    note: string;
}

type FxOrientation = 'PGK_TO_FCY' | 'FCY_TO_PGK';

const FX_DISPLAY_PRIORITY: Record<string, number> = {
    USD: 0,
    AUD: 1,
};

function parsePositiveNumber(value: string | number): number | null {
    const parsed = typeof value === 'number' ? value : parseFloat(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function getFxDisplayCurrency(rawCurrency: string): string | null {
    const normalized = (rawCurrency || '').toUpperCase();
    if (!normalized) {
        return null;
    }

    if (!normalized.includes('/')) {
        return normalized === 'PGK' ? null : normalized;
    }

    const [left, right] = normalized.split('/');
    if (left === 'PGK' && right && right !== 'PGK') {
        return right;
    }
    if (right === 'PGK' && left && left !== 'PGK') {
        return left;
    }

    return normalized;
}

function inferFxOrientation(rate: FxDisplayRateInput): FxOrientation {
    const normalizedCurrency = (rate.currency || '').toUpperCase();
    if (normalizedCurrency.includes('/')) {
        const [left, right] = normalizedCurrency.split('/');
        if (left === 'PGK' && right && right !== 'PGK') {
            return 'PGK_TO_FCY';
        }
        if (right === 'PGK' && left && left !== 'PGK') {
            return 'FCY_TO_PGK';
        }
    }

    const numericRates = [parsePositiveNumber(rate.tt_buy), parsePositiveNumber(rate.tt_sell)].filter(
        (value): value is number => value !== null,
    );

    if (numericRates.length > 0 && Math.max(...numericRates) < 1) {
        return 'PGK_TO_FCY';
    }

    return 'FCY_TO_PGK';
}

function convertForBusinessDirection(
    rawValue: number | null,
    orientation: FxOrientation,
    direction: 'FCY_TO_PGK' | 'PGK_TO_FCY',
): number | null {
    if (!rawValue) {
        return null;
    }

    if (direction === orientation) {
        return rawValue;
    }

    return 1 / rawValue;
}

export function buildFxDisplayRows(rate: FxDisplayRateInput): FxDisplayRow[] {
    const currency = getFxDisplayCurrency(rate.currency);
    if (!currency) {
        return [];
    }

    const orientation = inferFxOrientation(rate);
    const ttBuyValue = convertForBusinessDirection(parsePositiveNumber(rate.tt_buy), orientation, 'FCY_TO_PGK');
    const ttSellValue = convertForBusinessDirection(parsePositiveNumber(rate.tt_sell), orientation, 'PGK_TO_FCY');

    return [
        ttBuyValue
            ? {
                label: 'TT Buy',
                direction: `${currency} -> PGK`,
                from: currency,
                to: 'PGK',
                value: ttBuyValue,
                note: 'Used when converting FCY to PGK.',
            }
            : null,
        ttSellValue
            ? {
                label: 'TT Sell',
                direction: `PGK -> ${currency}`,
                from: 'PGK',
                to: currency,
                value: ttSellValue,
                note: 'Used when converting PGK to FCY.',
            }
            : null,
    ].filter((row): row is FxDisplayRow => row !== null);
}

export function compareFxDisplayCurrencies(leftRaw: string, rightRaw: string): number {
    const left = getFxDisplayCurrency(leftRaw) || leftRaw;
    const right = getFxDisplayCurrency(rightRaw) || rightRaw;
    const leftPriority = FX_DISPLAY_PRIORITY[left] ?? Number.MAX_SAFE_INTEGER;
    const rightPriority = FX_DISPLAY_PRIORITY[right] ?? Number.MAX_SAFE_INTEGER;

    if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
    }

    return left.localeCompare(right);
}

export function formatFxDisplayValue(value: number): string {
    return value.toFixed(4);
}
