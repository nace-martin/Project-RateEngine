"use client";

import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 aria-invalid:border-destructive",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 hover:shadow-md",
        destructive:
          "bg-destructive text-white shadow-sm hover:bg-destructive/90 focus-visible:ring-destructive/20",
        outline:
          "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
        ghost:
          "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
        success:
          "bg-emerald-600 text-white shadow-sm hover:bg-emerald-700 hover:shadow-md",
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
  onClick,
  disabled,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const [isPendingClick, setIsPendingClick] = React.useState(false)
  const clickLockRef = React.useRef(false)
  const Comp = asChild ? Slot : "button"

  const handleClick = React.useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (disabled || clickLockRef.current) {
      event.preventDefault()
      return
    }

    const result = onClick?.(event)
    if (isPromiseLike(result)) {
      clickLockRef.current = true
      setIsPendingClick(true)
      void result.finally(() => {
        clickLockRef.current = false
        setIsPendingClick(false)
      })
    }
  }, [disabled, onClick])

  if (asChild) {
    return (
      <Comp
        data-slot="button"
        className={cn(buttonVariants({ variant, size, className }))}
        onClick={onClick}
        disabled={disabled}
        {...props}
      />
    )
  }

  const resolvedDisabled = Boolean(disabled || isPendingClick)

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      onClick={handleClick}
      disabled={resolvedDisabled}
      aria-busy={isPendingClick || undefined}
      {...props}
    />
  )
}

export { Button, buttonVariants }
