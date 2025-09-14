export interface AirportOption {
  code: string;
  name: string;
}

// PNG domestic airports (common/major). Extend as needed.
export const pngAirports: AirportOption[] = [
  { code: "POM", name: "Port Moresby (Jacksons)" },
  { code: "LAE", name: "Lae (Nadzab)" },
  { code: "HGU", name: "Mount Hagen (Kagamuga)" },
  { code: "GKA", name: "Goroka" },
  { code: "RAB", name: "Rabaul (Tokua)" },
  { code: "WWK", name: "Wewak (Boram)" },
  { code: "KVG", name: "Kavieng" },
  { code: "MAG", name: "Madang" },
  { code: "GUR", name: "Alotau (Gurney)" },
  { code: "TBG", name: "Tabubil" },
  { code: "HKN", name: "Hoskins (Kimbe)" },
  { code: "KIE", name: "Kieta (Aropa)" },
];

