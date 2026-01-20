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
    showMinCharge?: boolean;
    minChargeName?: `charges.${number}.min_charge`;
}

export function SmartMoneyInput({
    control,
    index,
    currencyName,
    amountName,
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
                                    <Input
                                        type="number"
                                        step="0.01"
                                        placeholder="0.00"
                                        {...field}
                                        className="h-9"
                                    />
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
                                <Input
                                    type="number"
                                    step="0.01"
                                    placeholder="Min"
                                    {...field}
                                    value={field.value || ""}
                                    className="h-8 text-xs bg-muted/20"
                                />
                            </FormControl>
                        </FormItem>
                    )}
                />
            )}
        </div>
    );
}
