"use client";

import { useState, useEffect } from "react";
import { Check, ChevronsUpDown, Loader2, X } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { searchLocations } from "@/lib/api";
import { LocationSearchResult } from "@/lib/types";
import { useAuth } from "@/context/auth-context";

interface LocationSearchComboboxProps {
  value: string | null;
  selectedLabel?: string | null;
  onSelect: (value: LocationSearchResult | null) => void;
  placeholder?: string;
  minSearchChars?: number;
}

const DEFAULT_MIN_CHARS = 2;

export default function LocationSearchCombobox({
  value,
  selectedLabel,
  onSelect,
  placeholder = "Search locations...",
  minSearchChars = DEFAULT_MIN_CHARS,
}: LocationSearchComboboxProps) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<LocationSearchResult[]>([]);

  useEffect(() => {
    if (!user || searchQuery.length < minSearchChars) {
      setResults([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    const timer = setTimeout(async () => {
      try {
        const data = await searchLocations(searchQuery);
        setResults(data);
      } catch (error) {
        console.error("Failed to fetch locations", error);
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, user, minSearchChars]);

  const handleSelect = (location: LocationSearchResult | null) => {
    onSelect(location);
    setOpen(false);
    setSearchQuery("");
  };

  const currentLabel = selectedLabel || value || placeholder;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
        >
          <span className="truncate">{currentLabel}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[320px] p-0">
        <Command>
          <CommandInput
            placeholder="Type 2+ chars to search"
            onValueChange={setSearchQuery}
          />
          <CommandList>
            {value && (
              <CommandItem
                value="clear"
                onSelect={() => handleSelect(null)}
                className="text-destructive"
              >
                <X className="mr-2 h-4 w-4" />
                Clear selection
              </CommandItem>
            )}
            {searchQuery.length < minSearchChars && (
              <div className="px-3 py-4 text-sm text-muted-foreground">
                Type at least {minSearchChars} characters to search.
              </div>
            )}
            {isLoading && (
              <div className="flex items-center justify-center gap-2 p-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading...
              </div>
            )}
            {!isLoading && searchQuery.length >= minSearchChars && results.length === 0 && (
              <CommandEmpty>No locations found.</CommandEmpty>
            )}
            <CommandGroup>
              {results.map((location) => (
                <CommandItem
                  key={`${location.type}-${location.id}`}
                  value={`${location.display_name} ${location.code} ${location.type}`}
                  onSelect={() => handleSelect(location)}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === location.id ? "opacity-100" : "opacity-0",
                    )}
                  />
                  <div className="flex flex-col">
                    <span className="font-medium">{location.display_name}</span>
                    <span className="text-xs text-muted-foreground">
                      {location.code} • {location.type.toUpperCase()}
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
