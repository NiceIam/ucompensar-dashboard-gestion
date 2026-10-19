import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

/*
 * Tamaños pensados para el dedo: en pantallas pequeñas los botones miden al
 * menos 44 px de alto; desde `sm` se vuelven un poco más compactos.
 */
const buttonVariants = cva(
  "relative inline-flex select-none items-center justify-center whitespace-nowrap rounded-xl text-sm font-semibold ring-offset-background transition-[background-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-busy:cursor-progress [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          // El hover usa un tono propio (no opacidad): aclarar el naranja bajaría el contraste del texto blanco.
          "bg-primary text-primary-foreground shadow-[0_1px_0_hsl(0_0%_100%/0.12)_inset,0_1px_2px_hsl(var(--shadow)/0.2)] hover:bg-primary-hover",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-danger-strong dark:hover:bg-destructive/90",
        outline:
          "border border-input bg-card text-foreground hover:border-foreground/25 hover:bg-accent",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/70",
        soft: "bg-primary-soft text-primary-strong hover:bg-primary-soft/70",
        highlight:
          "bg-highlight text-highlight-foreground hover:bg-highlight/90",
        ghost: "text-foreground/80 hover:bg-accent hover:text-foreground",
        link: "h-auto px-0 text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 gap-2 px-4 sm:h-10",
        sm: "h-11 gap-1.5 rounded-lg px-3 text-[13px] sm:h-9",
        lg: "h-12 gap-2 px-6 text-[15px]",
        icon: "h-11 w-11 sm:h-10 sm:w-10",
        "icon-sm": "h-11 w-11 rounded-lg sm:h-9 sm:w-9",
        "icon-xs": "h-11 w-11 rounded-lg sm:h-8 sm:w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  /** Muestra un indicador de carga, bloquea el botón y avisa a lectores de pantalla. */
  loading?: boolean
  /** Texto opcional mientras carga (si no, se conserva el texto original). */
  loadingText?: React.ReactNode
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, loadingText, children, disabled, ...props }, ref) => {
    if (asChild) {
      // asChild simple: clona el hijo con las clases del botón
      const child = React.Children.only(children as React.ReactElement)
      return React.cloneElement(child, {
        className: cn(
          buttonVariants({ variant, size }),
          className,
          (child.props as { className?: string }).className
        ),
        ref,
      })
    }

    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? (
          <>
            <Loader2 className="animate-spin" aria-hidden="true" />
            {loadingText ?? children}
          </>
        ) : (
          children
        )}
      </button>
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
