export const DISCOUNT_CSV_TEMPLATE = [
  'product_code,discount_type,discount_value,currency,min_charge,max_charge,valid_from,valid_until,notes',
  'IMP-CLEAR,PERCENTAGE,10,PGK,,,2026-01-01,2026-12-31,Contract discount',
  'IMP-DOC-DEST,FLAT_AMOUNT,15,PGK,,,,,Docs reduction',
].join('\n');

export function downloadDiscountCsvTemplate() {
  const blob = new Blob([DISCOUNT_CSV_TEMPLATE], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'negotiated-pricing-template.csv';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
