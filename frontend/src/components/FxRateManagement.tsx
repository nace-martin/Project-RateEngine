'use client';

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AlertCircle, CheckCircle2, RefreshCw, AlertTriangle } from 'lucide-react';
import { API_BASE_URL } from '@/lib/config';

interface CurrencyRate {
    currency: string;
    tt_buy: string;
    tt_sell: string;
}

interface FxStatus {
    rates: CurrencyRate[];
    last_updated: string | null;
    source: string | null;
    is_stale: boolean;
    staleness_hours: number | null;
    staleness_warning: string | null;
}

interface RateInput {
    tt_buy: string;
    tt_sell: string;
}

interface Props {
    canEditFxRates?: boolean;
}

export default function FxRateManagement({ canEditFxRates = false }: Props) {
    const [status, setStatus] = useState<FxStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const [showForm, setShowForm] = useState(false);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);

    // Form state for manual rate entry
    const [rateInputs, setRateInputs] = useState<Record<string, RateInput>>({
        AUD: { tt_buy: '', tt_sell: '' },
        USD: { tt_buy: '', tt_sell: '' },
    });
    const [note, setNote] = useState('');

    const fetchStatus = async () => {
        setLoading(true);
        setError(null);
        try {
            const token = localStorage.getItem('authToken');
            const response = await fetch(`${API_BASE_URL}/api/v4/fx/status/`, {
                headers: {
                    'Authorization': token ? `Token ${token}` : '',
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                throw new Error(`Failed to fetch FX status: ${response.statusText}`);
            }

            const data = await response.json();
            setStatus(data);

            // Pre-populate form with current rates if available
            if (data.rates?.length > 0) {
                const newInputs: Record<string, RateInput> = {};
                data.rates.forEach((rate: CurrencyRate) => {
                    newInputs[rate.currency] = {
                        tt_buy: rate.tt_buy,
                        tt_sell: rate.tt_sell,
                    };
                });
                // Ensure AUD and USD exist
                if (!newInputs.AUD) newInputs.AUD = { tt_buy: '', tt_sell: '' };
                if (!newInputs.USD) newInputs.USD = { tt_buy: '', tt_sell: '' };
                setRateInputs(newInputs);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load FX status');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStatus();
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitting(true);
        setError(null);
        setSuccessMessage(null);

        try {
            const token = localStorage.getItem('authToken');

            // Build rates object, filtering out empty entries
            const rates: Record<string, { tt_buy: number; tt_sell: number }> = {};
            Object.entries(rateInputs).forEach(([currency, values]) => {
                if (values.tt_buy && values.tt_sell) {
                    rates[currency] = {
                        tt_buy: parseFloat(values.tt_buy),
                        tt_sell: parseFloat(values.tt_sell),
                    };
                }
            });

            if (Object.keys(rates).length === 0) {
                throw new Error('Please enter at least one currency rate');
            }

            const response = await fetch(`${API_BASE_URL}/api/v4/fx/manual-update/`, {
                method: 'POST',
                headers: {
                    'Authorization': token ? `Token ${token}` : '',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ rates, note }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to update FX rates');
            }

            const result = await response.json();
            setSuccessMessage(`Successfully updated ${result.updated_rates?.length || 0} currency rates`);
            setShowForm(false);
            setNote('');

            // Refresh status
            await fetchStatus();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update FX rates');
        } finally {
            setSubmitting(false);
        }
    };

    const handleInputChange = (currency: string, field: 'tt_buy' | 'tt_sell', value: string) => {
        setRateInputs(prev => ({
            ...prev,
            [currency]: {
                ...prev[currency],
                [field]: value,
            },
        }));
    };

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return 'Never';
        const date = new Date(dateStr);
        return date.toLocaleString();
    };

    const getStalenessColor = () => {
        if (!status) return 'text-gray-500';
        if (status.is_stale) return 'text-red-500';
        if (status.staleness_hours && status.staleness_hours > 12) return 'text-yellow-500';
        return 'text-green-500';
    };

    const getStalenessIcon = () => {
        if (!status) return <AlertCircle className="h-5 w-5" />;
        if (status.is_stale) return <AlertCircle className="h-5 w-5" />;
        if (status.staleness_hours && status.staleness_hours > 12) return <AlertTriangle className="h-5 w-5" />;
        return <CheckCircle2 className="h-5 w-5" />;
    };

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            FX Rates
                            <span className={getStalenessColor()}>
                                {getStalenessIcon()}
                            </span>
                        </CardTitle>
                        <CardDescription>
                            Foreign exchange rates for quoting. Updated daily from BSP.
                        </CardDescription>
                    </div>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={fetchStatus}
                        disabled={loading}
                    >
                        <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                </div>
            </CardHeader>
            <CardContent>
                {loading && !status && (
                    <div className="text-center py-4 text-muted-foreground">Loading FX rates...</div>
                )}

                {error && (
                    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-3 mb-4">
                        <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
                    </div>
                )}

                {successMessage && (
                    <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md p-3 mb-4">
                        <p className="text-sm text-green-700 dark:text-green-400">{successMessage}</p>
                    </div>
                )}

                {status?.staleness_warning && (
                    <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md p-3 mb-4">
                        <p className="text-sm text-yellow-700 dark:text-yellow-400">{status.staleness_warning}</p>
                    </div>
                )}

                {status && (
                    <>
                        {/* Current Rates Display */}
                        <div className="space-y-4">
                            <div className="text-sm text-muted-foreground">
                                <span className="font-medium">Last Updated:</span> {formatDate(status.last_updated)}
                                {status.source && <span className="ml-2">({status.source})</span>}
                            </div>

                            {status.rates.length > 0 ? (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {status.rates
                                        .filter(rate => {
                                            // Exclude PGK-based pairs (PGK/*, or just "PGK")
                                            const baseCurrency = rate.currency.split('/')[0] || rate.currency;
                                            return baseCurrency !== 'PGK';
                                        })
                                        .map((rate) => {
                                            // Extract base currency from pair (e.g., "USD/PGK" -> "USD")
                                            const baseCurrency = rate.currency.split('/')[0] || rate.currency;
                                            const ttBuy = parseFloat(rate.tt_buy);
                                            const ttSell = parseFloat(rate.tt_sell);

                                            return (
                                                <div key={rate.currency} className="bg-muted/50 rounded-lg p-4 space-y-3">
                                                    <div className="font-semibold text-lg border-b pb-2">{baseCurrency}</div>

                                                    {/* FCY to PGK conversion */}
                                                    <div className="space-y-1">
                                                        <div className="text-xs text-muted-foreground uppercase tracking-wide">
                                                            {baseCurrency} → PGK
                                                        </div>
                                                        <div className="flex items-baseline gap-2">
                                                            <span className="text-sm text-muted-foreground">1 {baseCurrency} =</span>
                                                            <span className="font-mono font-semibold text-lg">{ttSell.toFixed(4)}</span>
                                                            <span className="text-sm text-muted-foreground">PGK</span>
                                                        </div>
                                                    </div>

                                                    {/* PGK to FCY conversion */}
                                                    <div className="space-y-1">
                                                        <div className="text-xs text-muted-foreground uppercase tracking-wide">
                                                            PGK → {baseCurrency}
                                                        </div>
                                                        <div className="flex items-baseline gap-2">
                                                            <span className="text-sm text-muted-foreground">1 PGK =</span>
                                                            <span className="font-mono font-semibold text-lg">{(1 / ttBuy).toFixed(4)}</span>
                                                            <span className="text-sm text-muted-foreground">{baseCurrency}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                </div>
                            ) : (
                                <div className="text-center py-4 text-muted-foreground">
                                    No FX rates available
                                </div>
                            )}
                        </div>

                        {/* Manual Entry Form (Finance/Admin only) */}
                        {canEditFxRates && (
                            <div className="mt-6 pt-6 border-t">
                                {!showForm ? (
                                    <Button onClick={() => setShowForm(true)} variant="outline">
                                        Enter Rates Manually
                                    </Button>
                                ) : (
                                    <form onSubmit={handleSubmit} className="space-y-4">
                                        <h4 className="font-medium">Manual Rate Entry</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Use this form if the automated BSP scraper has failed.
                                        </p>

                                        {['AUD', 'USD'].map((currency) => (
                                            <div key={currency} className="grid grid-cols-3 gap-4 items-end">
                                                <div className="font-medium">{currency}/PGK</div>
                                                <div>
                                                    <Label htmlFor={`${currency}-buy`}>TT Buy</Label>
                                                    <Input
                                                        id={`${currency}-buy`}
                                                        type="number"
                                                        step="0.0001"
                                                        min="0.0001"
                                                        placeholder="e.g., 2.7700"
                                                        value={rateInputs[currency]?.tt_buy || ''}
                                                        onChange={(e) => handleInputChange(currency, 'tt_buy', e.target.value)}
                                                    />
                                                </div>
                                                <div>
                                                    <Label htmlFor={`${currency}-sell`}>TT Sell</Label>
                                                    <Input
                                                        id={`${currency}-sell`}
                                                        type="number"
                                                        step="0.0001"
                                                        min="0.0001"
                                                        placeholder="e.g., 2.8500"
                                                        value={rateInputs[currency]?.tt_sell || ''}
                                                        onChange={(e) => handleInputChange(currency, 'tt_sell', e.target.value)}
                                                    />
                                                </div>
                                            </div>
                                        ))}

                                        <div>
                                            <Label htmlFor="note">Note (optional)</Label>
                                            <Input
                                                id="note"
                                                type="text"
                                                placeholder="Reason for manual entry"
                                                value={note}
                                                onChange={(e) => setNote(e.target.value)}
                                            />
                                        </div>

                                        <div className="flex gap-2">
                                            <Button type="submit" disabled={submitting}>
                                                {submitting ? 'Updating...' : 'Update Rates'}
                                            </Button>
                                            <Button
                                                type="button"
                                                variant="outline"
                                                onClick={() => setShowForm(false)}
                                                disabled={submitting}
                                            >
                                                Cancel
                                            </Button>
                                        </div>
                                    </form>
                                )}
                            </div>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    );
}
