"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

type SelectOnChange = (value: string) => void

export interface SelectRootProps {
  value?: string
  onValueChange?: SelectOnChange
  required?: boolean
  className?: string
  id?: string
  children: React.ReactNode
}

// Internal element markers
const SelectTriggerMarker = (props: any) => null
SelectTriggerMarker.displayName = "SelectTrigger"

const SelectValueMarker = (props: { placeholder?: string }) => null
SelectValueMarker.displayName = "SelectValue"

const SelectContentMarker = (props: any) => null
SelectContentMarker.displayName = "SelectContent"

export interface SelectItemProps {
  value: string
  children: React.ReactNode
}

const SelectItem: React.FC<SelectItemProps> = () => null
SelectItem.displayName = "SelectItem"

function isElementOf(el: any, comp: any) {
  return React.isValidElement(el) && (el.type as any)?.displayName === comp.displayName
}

const Select: React.FC<SelectRootProps> = ({ value, onValueChange, required, className, id, children }) => {
  // Extract structure from children
  let triggerId: string | undefined = id
  let placeholder: string | undefined
  const items: { value: string; label: React.ReactNode }[] = []

  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return
    // Trigger block
    if (isElementOf(child, SelectTriggerMarker)) {
      const trigProps: any = child.props || {}
      triggerId = triggerId || trigProps.id
      React.Children.forEach(trigProps.children, (grand) => {
        if (isElementOf(grand, SelectValueMarker)) {
          placeholder = (grand.props || {}).placeholder
        }
      })
    }
    // Content block
    if (isElementOf(child, SelectContentMarker)) {
      const contentProps: any = child.props || {}
      React.Children.forEach(contentProps.children, (grand) => {
        if (isElementOf(grand, SelectItem)) {
          items.push({ value: grand.props.value, label: grand.props.children })
        }
      })
    }
  })

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onValueChange?.(e.target.value)
  }

  return (
    <select
      id={triggerId}
      value={value}
      onChange={handleChange}
      required={required}
      className={cn(
        "flex h-10 w-full appearance-none rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-900",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900",
        "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
    >
      {placeholder && (
        <option value="" disabled hidden className="bg-slate-50 text-slate-500 dark:bg-slate-900 dark:text-slate-400">
          {placeholder}
        </option>
      )}
      {items.map((opt) => (
        <option
          key={opt.value}
          value={opt.value}
          className="bg-slate-50 text-slate-900 dark:bg-slate-800 dark:text-slate-100"
        >
          {opt.label}
        </option>
      ))}
    </select>
  )
}

// Re-export component names used by callers
const SelectTrigger = SelectTriggerMarker as unknown as React.FC<React.HTMLAttributes<HTMLDivElement> & { id?: string }>
const SelectValue = SelectValueMarker as unknown as React.FC<{ placeholder?: string }>
const SelectContent = SelectContentMarker as unknown as React.FC<{ children?: React.ReactNode }>

export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem }
