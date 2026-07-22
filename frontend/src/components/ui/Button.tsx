import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const STYLES: Record<Variant, string> = {
  primary:
    "bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-[0_0_20px_-6px_rgba(139,92,246,0.7)] hover:shadow-[0_0_24px_-4px_rgba(139,92,246,0.9)] hover:brightness-110 disabled:opacity-40 disabled:shadow-none",
  secondary:
    "bg-white/[0.06] text-white/80 border border-white/15 hover:bg-white/10 hover:text-white disabled:opacity-40",
  ghost: "bg-transparent text-white/60 hover:bg-white/[0.06] hover:text-white",
  danger: "bg-red-500/90 text-white hover:bg-red-500 disabled:opacity-40",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({ variant = "primary", className = "", children, ...rest }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition-all focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-1 focus:ring-offset-[#0b0713] ${STYLES[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
