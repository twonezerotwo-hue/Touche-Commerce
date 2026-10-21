import * as React from "react";
import { CircleAlert, CircleCheck, Info } from "lucide-react";

import { cn } from "@/lib/utils";

type AlertVariant = "danger" | "warning" | "success" | "info";

const ALERT_STYLES: Record<AlertVariant, string> = {
  danger: "border-crimson-400/35 bg-crimson-400/[0.08] text-crimson-400",
  warning: "border-amber-400/35 bg-amber-400/[0.08] text-amber-400",
  success: "border-jade-400/35 bg-jade-400/[0.08] text-jade-400",
  info: "border-white/10 bg-white/[0.03] text-mist-300",
};

const ALERT_ICONS = {
  danger: CircleAlert,
  warning: CircleAlert,
  success: CircleCheck,
  info: Info,
} as const;

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: AlertVariant;
  title?: string;
}

function Alert({ className, variant = "danger", title, children, ...props }: AlertProps) {
  const Icon = ALERT_ICONS[variant];
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(
        "flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-[12px] leading-relaxed",
        ALERT_STYLES[variant],
        className,
      )}
      {...props}
    >
      <Icon className="mt-[1px] size-3.5 shrink-0" aria-hidden />
      <div className="min-w-0">
        {title ? <p className="font-medium">{title}</p> : null}
        <div className={cn(title && "mt-0.5", "text-mist-300")}>{children}</div>
      </div>
    </div>
  );
}

export { Alert };
