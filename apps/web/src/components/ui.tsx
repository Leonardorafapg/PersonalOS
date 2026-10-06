"use client";

import clsx from "clsx";
import { Check as CheckIcon, Loader2, Sparkles, X } from "lucide-react";
import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export const cx = clsx;

export const inputCls =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] text-text placeholder:text-faint outline-none transition focus:border-ink focus:ring-2 focus:ring-ink/10 disabled:opacity-50";

export function Button({
  variant = "primary",
  size = "md",
  className,
  loading,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "soft" | "ghost" | "danger" | "accent";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition active:scale-[.98] disabled:opacity-50 disabled:active:scale-100",
        size === "md" ? "min-h-11 px-4 text-[15px]" : "min-h-8 px-3 text-sm",
        variant === "primary" && "bg-ink text-inkfg hover:opacity-90",
        variant === "accent" && "bg-accent text-accentfg hover:opacity-90",
        variant === "soft" && "bg-surface2 text-text hover:bg-line/60",
        variant === "ghost" && "text-muted hover:bg-surface2 hover:text-text",
        variant === "danger" && "text-danger hover:bg-danger/10",
        className,
      )}
    >
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

export function IconButton({
  label,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...rest}
      aria-label={label}
      title={label}
      className={cx(
        "inline-grid size-10 place-items-center rounded-full text-muted transition hover:bg-surface2 hover:text-text active:scale-95",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center" role="dialog" aria-modal="true">
      <div className="anim-fade absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} />
      <div
        ref={ref}
        className={cx(
          "anim-sheet relative flex max-h-[92dvh] w-full flex-col rounded-t-3xl border border-line bg-surface shadow-2xl md:rounded-3xl",
          wide ? "md:max-w-2xl" : "md:max-w-lg",
        )}
      >
        <div className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-line md:hidden" />
        <div className="flex items-center justify-between gap-3 px-5 pb-2 pt-3">
          <h2 className="min-w-0 truncate text-lg font-semibold tracking-tight">{title}</h2>
          <IconButton label="Fechar" onClick={onClose} className="-mr-2 shrink-0">
            <X className="size-5" />
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">{children}</div>
        {footer && (
          <div className="shrink-0 border-t border-line px-5 py-3" style={{ paddingBottom: "max(12px, var(--safe-bottom))" }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1.5 block text-[13px] font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  className?: string;
}) {
  return (
    <div className={cx("inline-flex w-full rounded-xl bg-surface2 p-1", className)} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "min-h-8 flex-1 whitespace-nowrap rounded-lg px-3 text-sm font-medium transition",
            value === o.value ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Check({ checked, onChange, label, size = 24, tone }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; size?: number; tone?: string;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      className="grid shrink-0 place-items-center rounded-full p-2 -m-2"
    >
      <span
        className={cx(
          "grid place-items-center rounded-full border-[1.5px] transition",
          checked ? "border-transparent bg-ok text-white" : "border-faint hover:border-text",
        )}
        style={{ width: size, height: size, ...(tone && !checked ? { borderColor: tone } : {}) }}
      >
        {checked && <CheckIcon className="size-[62%]" strokeWidth={3} />}
      </span>
    </button>
  );
}

export function Chip({ children, tone, className }: { children: ReactNode; tone?: "accent" | "danger" | "muted" | "ok"; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        !tone && "bg-surface2 text-muted",
        tone === "muted" && "bg-surface2 text-muted",
        tone === "accent" && "bg-accent/12 text-accent",
        tone === "danger" && "bg-danger/12 text-danger",
        tone === "ok" && "bg-ok/12 text-ok",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function ClaudeBadge({ className }: { className?: string }) {
  return (
    <span title="Criado pelo Claude" className={cx("inline-flex items-center text-accent", className)}>
      <Sparkles className="size-3" aria-label="Claude" />
    </span>
  );
}

export function Bar({ value, className, tone = "ink" }: { value: number; className?: string; tone?: "ink" | "ok" | "accent" }) {
  return (
    <div className={cx("h-1.5 overflow-hidden rounded-full bg-surface2", className)}>
      <div
        className={cx("h-full rounded-full transition-all", tone === "ink" && "bg-ink", tone === "ok" && "bg-ok", tone === "accent" && "bg-accent")}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function Ring({ value, size = 64, stroke = 6, children }: { value: number; size?: number; stroke?: number; children?: ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(0, Math.min(1, value)))}
          style={{ transition: "stroke-dashoffset .5s ease" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-sm font-semibold tabular-nums">{children}</div>
    </div>
  );
}

export function Empty({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      {icon && <div className="mb-1 grid size-12 place-items-center rounded-2xl bg-surface2 text-muted">{icon}</div>}
      <p className="font-medium">{title}</p>
      {hint && <p className="max-w-xs text-sm text-muted">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("size-5 animate-spin text-muted", className)} />;
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2 mt-6 flex items-center justify-between px-1">
      <h3 className="text-[13px] font-semibold uppercase tracking-wider text-muted">{children}</h3>
      {right}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cx("relative h-7 w-12 shrink-0 rounded-full transition", checked ? "bg-ink" : "bg-line")}
    >
      <span className={cx("absolute top-0.5 size-6 rounded-full bg-surface shadow transition-all", checked ? "left-[22px]" : "left-0.5")} />
    </button>
  );
}
