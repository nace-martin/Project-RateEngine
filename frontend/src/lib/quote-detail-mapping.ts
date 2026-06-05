import type { QuoteComputeResult, V3QuoteComputeResponse } from './types';

export function mapQuoteDetailToComputeResult(quote: V3QuoteComputeResponse): QuoteComputeResult {
  const canonicalResult = quote.quote_result ?? null;
  const version = quote.latest_version;
  const totals = version?.totals;
  const lines = version?.lines ?? [];
  const displayCurrency =
    canonicalResult?.currency ||
    totals?.currency ||
    totals?.total_sell_fcy_currency ||
    quote.output_currency ||
    'PGK';

  const exchange_rates: Record<string, string> = {};
  for (const line of lines) {
    const rate = line.exchange_rate;
    const ccy = (line.cost_fcy_currency || line.sell_fcy_currency || '').toUpperCase();
    if (!rate || !ccy || ccy === 'PGK') continue;
    exchange_rates[`${ccy}/PGK`] = rate;
  }

  return {
    quote_id: canonicalResult?.quote_id || quote.id,
    quote_number: quote.quote_number,
    buy_lines: [],
    sell_lines: lines.map((line) => {
      const sellCurrency = line.sell_fcy_currency || displayCurrency;
      const lineGstAmount =
        (sellCurrency || '').toUpperCase() !== 'PGK'
          ? (parseFloat(line.sell_fcy_incl_gst || '0') - parseFloat(line.sell_fcy || '0'))
          : (parseFloat(line.sell_pgk_incl_gst || '0') - parseFloat(line.sell_pgk || '0'));
      return {
        line_type: 'COMPONENT',
        component: line.product_code || line.component || line.service_component?.code || null,
        description: line.description || line.cost_source_description || line.service_component?.description || 'Charge',
        leg: line.service_component?.leg || undefined,
        cost_pgk: line.cost_pgk,
        sell_pgk: line.sell_pgk,
        sell_pgk_incl_gst: line.sell_pgk_incl_gst,
        gst_amount: lineGstAmount.toFixed(2),
        sell_fcy: line.sell_fcy,
        sell_fcy_incl_gst: line.sell_fcy_incl_gst,
        sell_currency: sellCurrency,
        margin_percent: '0',
        exchange_rate: line.exchange_rate || '0',
        source: line.cost_source || 'stored_quote',
        is_informational: false,
      };
    }),
    totals: {
      total_sell_ex_gst:
        displayCurrency.toUpperCase() !== 'PGK'
          ? (totals?.total_sell_fcy || totals?.total_sell_pgk || '0')
          : (totals?.total_sell_pgk || '0'),
      cost_pgk: totals?.total_cost_pgk || '0',
      sell_pgk: totals?.total_sell_pgk || '0',
      sell_pgk_incl_gst: totals?.total_sell_pgk_incl_gst || totals?.total_sell_pgk || '0',
      gst_amount: (
        displayCurrency.toUpperCase() !== 'PGK'
          ? (
            (parseFloat(totals?.total_sell_fcy_incl_gst || totals?.total_sell_fcy || '0')) -
            (parseFloat(totals?.total_sell_fcy || '0'))
          )
          : (
            (parseFloat(totals?.total_sell_pgk_incl_gst || totals?.total_sell_pgk || '0')) -
            (parseFloat(totals?.total_sell_pgk || '0'))
          )
      ).toFixed(2),
      caf_pgk: '0',
      currency: displayCurrency,
      total_sell_fcy: totals?.total_sell_fcy || totals?.total_sell_pgk || '0',
      total_sell_fcy_incl_gst: totals?.total_sell_fcy_incl_gst || totals?.total_sell_pgk_incl_gst || '0',
      total_quote_amount:
        displayCurrency.toUpperCase() !== 'PGK'
          ? (totals?.total_sell_fcy_incl_gst || totals?.total_sell_fcy || '0')
          : (totals?.total_sell_pgk_incl_gst || totals?.total_sell_pgk || '0'),
      total_sell_fcy_currency: totals?.total_sell_fcy_currency || displayCurrency,
    },
    exchange_rates,
    computation_date: canonicalResult?.calculated_at || version?.created_at || quote.updated_at || quote.created_at,
    notes: canonicalResult?.warnings?.length ? canonicalResult.warnings : (totals?.notes ? [totals.notes] : []),
    quote_result: canonicalResult,
  };
}
