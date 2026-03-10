import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FormControl, FormField, FormItem } from "@/components/ui/form";
import { Control } from "react-hook-form";
import type { SpotFormValues } from "@/lib/schemas/spotSchema";

interface SmartMoneyInputProps {
    control: Control<SpotFormValues>;
    index: number;
    currencyName: `charges.${number}.currency`;
    amountName: `charges.${number}.amount`;
    unit?: string;
    showMinCharge?: boolean;
    minChargeName?: `charges.${number}.min_charge`;
}

export function SmartMoneyInput({
    control,
    currencyName,
    amountName,
    unit,
    showMinCharge,
    minChargeName
}: SmartMoneyInputProps) {
    return (
        <div className="flex flex-col gap-2">
            <div className="flex gap-2">
                <div className="w-[80px]">
                    <FormField
                        control={control}
                        name={currencyName}
                        render={({ field }) => (
                            <FormItem>
                                <Select onValueChange={field.onChange} defaultValue={field.value}>
                                    <FormControl>
                                        <SelectTrigger className="h-9 px-2">
                                            <SelectValue />
                                        </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                        {["SGD", "USD", "AUD", "PGK", "NZD", "HKD"].map(c => (
                                            <SelectItem key={c} value={c}>{c}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </FormItem>
                        )}
                    />
                </div>
                <div className="flex-1">
                    <FormField
                        control={control}
                        name={amountName}
                        render={({ field }) => (
                            <FormItem>
                                <FormControl>
                                    <div className="relative">
                                        <Input
                                            type="number"
                                            step="0.01"
                                            placeholder="0.00"
                                            {...field}
                                            className={`h-9 ${unit === 'percentage' ? 'pr-8' : ''}`}
                                        />
                                        {unit === 'percentage' && (
                                            <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                                                <span className="text-muted-foreground text-sm font-medium">%</span>
                                            </div>
                                        )}
                                    </div>
                                </FormControl>
                            </FormItem>
                        )}
                    />
                </div>
            </div>

            {showMinCharge && minChargeName && (
                <FormField
                    control={control}
                    name={minChargeName}
                    render={({ field }) => (
                        <FormItem>
                            <FormControl>
                                <div className="relative">
                                    <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none">
                                        <span className="text-xs text-muted-foreground font-medium">Min:</span>
                                    </div>
                                    <Input
                                        type="number"
                                        step="0.01"
                                        placeholder="0.00"
                                        {...field}
                                        value={field.value || ""}
                                        className="h-8 text-xs bg-muted/20 pl-9"
                                    />
                                </div>
                            </FormControl>
                        </FormItem>
                    )}
                />
            )}
        </div>
    );
}
