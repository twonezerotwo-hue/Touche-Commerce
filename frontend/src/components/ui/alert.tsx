import * as React from "react";
import { CircleAlert, CircleCheck, Info } from "lucide-react";

import { cn } from "@/lib/utils";

type AlertVariant = "danger" | "warning" | "success" | "info";

const ALERT_STYLES: Record<AlertVariant, { frame: string; icon: string }> = {
  danger: {
    frame: "border-crimson-400/30 bg-crimson-400/[0.07]",
    icon: "text-crimson-400",
  },
  warning: {
    frame: "border-amber-400/30 bg-amber-400/[0.07]",
    icon: "text-amber-400",
  },
  success: {
    frame: "border-jade-400/30 bg-jade-400/[0.07]",
    icon: "text-jade-400",
  },
  info: {
    frame: "border-white/10 bg-white/[0.03]",
    icon: "text-accent-300",
  },
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
  const styles = ALERT_STYLES[variant];
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(
        "flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-[12px] leading-relaxed",
        styles.frame,
        className,
      )}
      {...props}
    >
      <Icon className={cn("mt-[1px] size-3.5 shrink-0", styles.icon)} aria-hidden />
      <div className="min-w-0">
        {title ? <p className="text-[12px] font-medium text-mist-100">{title}</p> : null}
        <div className={cn(title && "mt-0.5", "text-mist-300")}>{children}</div>
      </div>
    </div>
  );
}

export { Alert };
