"use client";

import * as React from "react";
import { Check, ChevronsUpDown } from "lucide-react";

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

type Option = {
  label: string;
  value: string;
};

type ComboboxProps = {
  options: Option[];
  placeholder?: string;
  emptyMessage?: string;
  value?: string;
  onChange?: (value: string) => void;
  className?: string;
  disabled?: boolean;
  buttonClassName?: string;
};

export function Combobox({
  options,
  placeholder = "Search...",
  emptyMessage = "No results found.",
  value,
  onChange,
  className,
  disabled,
  buttonClassName,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "h-9 w-full justify-between rounded-md border-input bg-background text-foreground transition-all duration-200 hover:border-primary/40 hover:bg-accent/60 active:border-primary/60 aria-expanded:border-primary/60 aria-expanded:shadow-sm",
            buttonClassName
          )}
          disabled={disabled}
        >
          <span className={cn("truncate", selected ? "font-medium text-foreground" : "text-muted-foreground")}>
            {selected ? selected.label : "Select..."}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 text-slate-500" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className={cn("w-[var(--radix-popover-trigger-width)] p-0", className)}>
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            <CommandGroup>
              {options.map((opt) => (
                <CommandItem
                  key={opt.value}
                  value={opt.label}
                  onSelect={() => {
                    onChange?.(opt.value);
                    setOpen(false);
                  }}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === opt.value ? "opacity-100" : "opacity-0"
                    )}
                  />
                  {opt.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
