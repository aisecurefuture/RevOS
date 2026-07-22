import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const STYLES: Record<Variant, string> = {
  primary:
    "bg-gradient-to-br from-violet-600 to-fuchsia-600 text-white shadow-sm shadow-violet-500/25 hover:shadow-md hover:shadow-violet-500/30 hover:brightness-105 disabled:opacity-40 disabled:shadow-none",
  secondary:
    "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 disabled:opacity-50",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-100",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:opacity-50",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({ variant = "primary", className = "", children, ...rest }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition-all focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-1 ${STYLES[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
