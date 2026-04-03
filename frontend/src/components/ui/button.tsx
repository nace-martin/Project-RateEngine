"use client";

import * as React from "react"
import { Loader2 } from "lucide-react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const CLICK_GUARD_MS = 500
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all duration-200 hover:-translate-y-px active:translate-y-0 active:scale-[0.98] disabled:pointer-events-none disabled:translate-y-0 disabled:shadow-none disabled:opacity-50 disabled:cursor-not-allowed aria-busy:cursor-progress data-[pending=true]:translate-y-0 data-[pending=true]:scale-100 data-[pending=true]:shadow-none data-[pending=true]:ring-2 data-[pending=true]:ring-primary/15 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 aria-invalid:border-destructive",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 hover:shadow-md active:bg-primary/95 active:shadow-sm",
        destructive:
          "bg-destructive text-white shadow-sm hover:bg-destructive/90 hover:shadow-md active:bg-destructive/95 active:shadow-sm focus-visible:ring-destructive/20",
        outline:
          "border border-input bg-background shadow-sm hover:border-primary/40 hover:bg-accent/70 hover:text-foreground hover:shadow-sm active:border-primary/60 active:bg-primary/5 active:shadow-none",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80 hover:shadow-sm active:bg-secondary/90 active:shadow-none",
        ghost:
          "hover:bg-accent/80 hover:text-accent-foreground active:bg-accent/90",
        link: "text-primary underline-offset-4 hover:underline",
        success:
          "bg-emerald-600 text-white shadow-sm hover:bg-emerald-700 hover:shadow-md active:bg-emerald-800 active:shadow-sm",
      },
      size: {
        default: "h-8 px-4 py-1.5 has-[>svg]:px-3 text-sm",
        sm: "h-7 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 text-xs",
        lg: "h-9 rounded-md px-6 has-[>svg]:px-4 text-sm",
        icon: "size-8",
        "icon-sm": "size-7",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const isPromiseLike = (value: unknown): value is Promise<unknown> =>
  !!value &&
  (typeof value === "object" || typeof value === "function") &&
  "then" in (value as Record<string, unknown>) &&
  typeof (value as { then?: unknown }).then === "function"

function Button({
  className,
  variant,
  size,
  asChild = false,
  children,
  onClick,
  type,
  disabled,
  loading = false,
  loadingText,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    loading?: boolean
    loadingText?: React.ReactNode
  }) {
  const [isPendingClick, setIsPendingClick] = React.useState(false)
  const [isClickGuarded, setIsClickGuarded] = React.useState(false)
  const clickLockRef = React.useRef(false)
  const clickGuardTimerRef = React.useRef<number | null>(null)
  const pendingTimerRef = React.useRef<number | null>(null)
  const Comp = asChild ? Slot : "button"
  const resolvedLoading = Boolean(loading || isPendingClick)

  const clearClickGuard = React.useCallback(() => {
    if (clickGuardTimerRef.current !== null) {
      window.clearTimeout(clickGuardTimerRef.current)
      clickGuardTimerRef.current = null
    }
    setIsClickGuarded(false)
  }, [])

  const clearPending = React.useCallback(() => {
    if (pendingTimerRef.current !== null) {
      window.clearTimeout(pendingTimerRef.current)
      pendingTimerRef.current = null
    }
    clickLockRef.current = false
    setIsPendingClick(false)
  }, [])

  const startClickGuard = React.useCallback((durationMs = CLICK_GUARD_MS) => {
    clearClickGuard()
    clickLockRef.current = true
    setIsClickGuarded(true)
    clickGuardTimerRef.current = window.setTimeout(() => {
      clickLockRef.current = false
      setIsClickGuarded(false)
      clickGuardTimerRef.current = null
    }, durationMs)
  }, [clearClickGuard])

  const startPending = React.useCallback((fallbackMs?: number) => {
    clearClickGuard()
    clearPending()
    clickLockRef.current = true
    setIsPendingClick(true)
    if (typeof fallbackMs === "number") {
      pendingTimerRef.current = window.setTimeout(() => {
        clearPending()
      }, fallbackMs)
    }
  }, [clearClickGuard, clearPending])

  React.useEffect(() => {
    return () => {
      clearClickGuard()
      clearPending()
    }
  }, [clearClickGuard, clearPending])

  const handleClick = React.useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (disabled || loading || clickLockRef.current) {
      event.preventDefault()
      return
    }

    const button = event.currentTarget
    const form = button.form ?? button.closest("form")
    const buttonType = type ?? (form ? "submit" : "button")

    if (buttonType !== "submit") {
      startClickGuard()
    }

    const result = onClick?.(event)
    if (isPromiseLike(result)) {
      startPending()
      void result.finally(() => {
        clearPending()
      })
    }
  }, [clearPending, disabled, loading, onClick, startClickGuard, startPending, type])

  const renderedChildren = resolvedLoading ? (
    <>
      <Loader2 className="animate-spin" />
      {loadingText ?? children}
    </>
  ) : children

  if (asChild) {
    return (
      <Comp
        data-slot="button"
        onClick={onClick}
        aria-busy={resolvedLoading || undefined}
        aria-disabled={disabled || resolvedLoading || undefined}
        data-pending={resolvedLoading ? "true" : undefined}
        className={cn(buttonVariants({ variant, size, className }), (disabled || resolvedLoading) && "pointer-events-none opacity-50")}
        {...props}
      >
        {children}
      </Comp>
    )
  }

  const resolvedDisabled = Boolean(disabled || resolvedLoading || isClickGuarded)

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      onClick={handleClick}
      type={type}
      disabled={resolvedDisabled}
      aria-busy={resolvedLoading || undefined}
      data-pending={resolvedLoading ? "true" : undefined}
      {...props}
    >
      {renderedChildren}
    </Comp>
  )
}

export { Button, buttonVariants }
