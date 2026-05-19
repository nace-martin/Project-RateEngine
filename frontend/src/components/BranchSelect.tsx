
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export const BRANCH_OPTIONS = [
  { value: "POM", label: "Port Moresby (POM)" },
  { value: "LAE", label: "Lae (LAE)" },
  { value: "BNE", label: "Brisbane (BNE)" },
  { value: "FIJ", label: "Fiji (FIJ)" },
  { value: "SOL", label: "Solomon Islands (SOL)" },
] as const;

interface BranchSelectProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function BranchSelect({
  value,
  onChange,
  placeholder = "Select branch",
  className,
  disabled,
}: BranchSelectProps) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger className={cn("w-full", className)}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {BRANCH_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
