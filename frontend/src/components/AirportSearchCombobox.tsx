"use client";

import { useState, useEffect } from "react";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { searchAirports } from "@/lib/api";
import { AirportSearchResult } from "@/lib/types";
import { useAuth } from "@/context/auth-context";

interface AirportSearchComboboxProps {
  value: string | null; // This will be the IATA code (e.g., "BNE")
  onSelect: (value: string | null) => void;
}

export default function AirportSearchCombobox({
  value,
  onSelect,
}: AirportSearchComboboxProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<AirportSearchResult[]>([]);
  const [selectedAirport, setSelectedAirport] =
    useState<AirportSearchResult | null>(null);

  // Fetch results when search query changes
  useEffect(() => {
    if (!user || searchQuery.length < 2) {
      setResults([]);
      return;
    }

    setIsLoading(true);
    const fetchAirports = async () => {
      try {
        const data = await searchAirports(searchQuery);
        setResults(data);
      } catch (error) {
        console.error("Failed to fetch airports", error);
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    };

    // Debounce the search
    const timer = setTimeout(fetchAirports, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, user]);

  // Update internal selected state if the parent 'value' changes
  useEffect(() => {
    if (value && !selectedAirport) {
      // This is a simplified lookup on mount, assumes 'value' is an IATA code
      // A more robust version might fetch the airport details by IATA code
      setSelectedAirport({ iata_code: value, name: value, city_country: "" });
    } else if (!value) {
      setSelectedAirport(null);
    }
  }, [value, selectedAirport]);

  const handleSelect = (airport: AirportSearchResult) => {
    setSelectedAirport(airport);
    onSelect(airport.iata_code);
    setOpen(false);
  };

  const currentSelectionLabel =
    selectedAirport?.iata_code || "Select airport...";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
        >
          {currentSelectionLabel}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0">
        <Command>
          <CommandInput
            placeholder="Search airport (e.g., BNE, POM, Brisbane)..."
            onValueChange={setSearchQuery}
          />
          <CommandList>
            {isLoading && (
              <div className="p-4 text-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin inline" />
                Loading...
              </div>
            )}
            {!isLoading && results.length === 0 && searchQuery.length > 1 && (
              <CommandEmpty>No airport found.</CommandEmpty>
            )}
            <CommandGroup>
              {results.map((airport) => (
                <CommandItem
                  key={airport.iata_code}
                  value={`${airport.iata_code} - ${airport.name} - ${airport.city_country}`}
                  onSelect={() => handleSelect(airport)}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === airport.iata_code ? "opacity-100" : "opacity-0",
                    )}
                  />
                  <div>
                    <span className="font-medium">{airport.iata_code}</span>
                    <span className="ml-2 text-muted-foreground">
                      {airport.name} ({airport.city_country})
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
