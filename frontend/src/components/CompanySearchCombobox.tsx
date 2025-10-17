// frontend/src/components/CompanySearchCombobox.tsx

'use client';

import { useEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { searchCompanies } from '@/lib/api';
import type { CompanySearchResult } from '@/lib/types';
import { cn } from '@/lib/utils';

interface CompanySearchComboboxProps {
  label?: string;
  placeholder?: string;
  value: CompanySearchResult | null;
  onSelect: (company: CompanySearchResult | null) => void;
  name?: string;
  helperText?: string;
  disabled?: boolean;
}

export default function CompanySearchCombobox({
  label,
  placeholder = 'Search for a company...',
  value,
  onSelect,
  name,
  helperText,
  disabled = false,
}: CompanySearchComboboxProps) {
  const [query, setQuery] = useState(value?.name ?? '');
  const [debouncedQuery, setDebouncedQuery] = useState(query);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<CompanySearchResult[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(value?.name ?? '');
  }, [value?.id, value?.name]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);

    return () => window.clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    const trimmed = debouncedQuery.trim();

    if (trimmed.length < 2) {
      setResults([]);
      setFetchError(null);
      setIsLoading(false);
      return;
    }

    let isActive = true;
    const controller = new AbortController();

    setIsLoading(true);
    setFetchError(null);

    searchCompanies(trimmed, controller.signal)
      .then((companies) => {
        if (!isActive) {
          return;
        }
        setResults(companies);
      })
      .catch((error: Error) => {
        if (!isActive || error.name === 'AbortError') {
          return;
        }
        setFetchError(error.message || 'Unable to fetch companies right now.');
        setResults([]);
      })
      .finally(() => {
        if (isActive) {
          setIsLoading(false);
        }
      });

    return () => {
      isActive = false;
      controller.abort();
    };
  }, [debouncedQuery]);

  useEffect(() => {
    const handleClickAway = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickAway);
    return () => document.removeEventListener('mousedown', handleClickAway);
  }, []);

  const handleSelect = (company: CompanySearchResult) => {
    setQuery(company.name);
    onSelect(company);
    setIsOpen(false);
  };

  const handleClear = () => {
    setQuery('');
    setResults([]);
    onSelect(null);
    setIsOpen(false);
  };

  return (
    <div className="space-y-2" ref={containerRef}>
      {label ? <Label htmlFor={name}>{label}</Label> : null}
      <div className="relative">
        <Input
          id={name}
          name={name}
          value={query}
          placeholder={placeholder}
          autoComplete="off"
          onFocus={() => setIsOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setIsOpen(true);
          }}
          disabled={disabled}
        />
        {value ? (
          <button
            type="button"
            className="absolute inset-y-0 right-2 flex items-center text-sm text-muted-foreground hover:text-foreground"
            onClick={handleClear}
            aria-label="Clear company selection"
          >
            ×
          </button>
        ) : null}
        {isOpen ? (
          <div className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-md border bg-background shadow-sm">
            {fetchError ? (
              <div className="px-3 py-2 text-sm text-destructive">{fetchError}</div>
            ) : null}
            {!fetchError && query.trim().length < 2 ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">
                Start typing at least two characters to search.
              </div>
            ) : null}
            {!fetchError && query.trim().length >= 2 && isLoading ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">Searching…</div>
            ) : null}
            {!fetchError && query.trim().length >= 2 && !isLoading && results.length === 0 ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">No companies found.</div>
            ) : null}
            {!fetchError && results.length > 0
              ? results.map((company) => (
                  <button
                    key={company.id}
                    type="button"
                    onClick={() => handleSelect(company)}
                    className={cn(
                      'flex w-full items-start px-3 py-2 text-left text-sm hover:bg-muted',
                      value?.id === company.id ? 'bg-muted' : ''
                    )}
                  >
                    <span className="font-medium">{company.name}</span>
                    <span className="ml-2 text-xs text-muted-foreground">{company.id}</span>
                  </button>
                ))
              : null}
          </div>
        ) : null}
      </div>
      {helperText ? <p className="text-sm text-muted-foreground">{helperText}</p> : null}
    </div>
  );
}
