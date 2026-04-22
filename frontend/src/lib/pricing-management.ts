export interface RateManagementLink {
  table: string;
  label: string;
  href: string;
}

export const RATE_MANAGEMENT_LINKS: RateManagementLink[] = [
  { table: 'ExportSellRate', label: 'Manage Export Sell', href: '/pricing/manage/export-sell' },
  { table: 'ExportCOGS', label: 'Manage Export COGS', href: '/pricing/manage/export-cogs' },
  { table: 'ImportSellRate', label: 'Manage Import Sell', href: '/pricing/manage/import-sell' },
  { table: 'ImportCOGS', label: 'Manage Import COGS', href: '/pricing/manage/import-cogs' },
  { table: 'DomesticSellRate', label: 'Manage Domestic Sell', href: '/pricing/manage/domestic-sell' },
  { table: 'DomesticCOGS', label: 'Manage Domestic COGS', href: '/pricing/manage/domestic-cogs' },
  { table: 'LocalSellRate', label: 'Manage Local Sell', href: '/pricing/manage/local-sell' },
  { table: 'LocalCOGSRate', label: 'Manage Local COGS', href: '/pricing/manage/local-cogs' },
];

export function getRateManagementLink(tableName: string): RateManagementLink | null {
  return RATE_MANAGEMENT_LINKS.find((link) => link.table === tableName) ?? null;
}
