import React from 'react';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface Column<T> {
    header: string;
    accessorKey?: keyof T;
    cell?: (item: T) => React.ReactNode;
    className?: string;
}

interface DataTableProps<T> {
    data: T[];
    columns: Column<T>[];
    keyExtractor: (item: T, index: number) => string;
    emptyMessage?: string;
    className?: string;
    onRowClick?: (item: T) => void;
}

export function DataTable<T>({
    data,
    columns,
    keyExtractor,
    emptyMessage = "No records found.",
    className,
    onRowClick,
}: DataTableProps<T>) {
    return (
        <div className={cn("rounded-md border border-border bg-card", className)}>
            <Table>
                <TableHeader className="bg-muted/50">
                    <TableRow>
                        {columns.map((col, index) => (
                            <TableHead
                                key={index}
                                className={cn("font-semibold text-muted-foreground", col.className)}
                            >
                                {col.header}
                            </TableHead>
                        ))}
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {data.length === 0 ? (
                        <TableRow>
                            <TableCell
                                colSpan={columns.length}
                                className="h-24 text-center text-muted-foreground"
                            >
                                {emptyMessage}
                            </TableCell>
                        </TableRow>
                    ) : (
                        data.map((item, index) => (
                            <TableRow
                                key={keyExtractor(item, index)}
                                className={cn(
                                    "hover:bg-muted/50 transition-colors",
                                    onRowClick && "cursor-pointer"
                                )}
                                onClick={() => onRowClick && onRowClick(item)}
                            >
                                {columns.map((col, colIndex) => (
                                    <TableCell key={colIndex} className={col.className}>
                                        {col.cell
                                            ? col.cell(item)
                                            : col.accessorKey
                                                ? (item[col.accessorKey] as React.ReactNode)
                                                : null
                                        }
                                    </TableCell>
                                ))}
                            </TableRow>
                        ))
                    )}
                </TableBody>
            </Table>
        </div>
    );
}
