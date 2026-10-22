import * as React from "react";

import { cn } from "@/lib/utils";

type CardVariant = "default" | "elevated" | "inset";

function Card({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<"div"> & { variant?: CardVariant }) {
  return (
    <div
      data-slot="card"
      className={cn(
        variant === "elevated" ? "panel-elevated" : variant === "inset" ? "panel-inset" : "panel",
        "text-mist-100",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn("flex items-start justify-between gap-4 px-5 pt-4.5", className)}
      {...props}
    />
  );
}

function CardHeading({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-heading" className={cn("min-w-0", className)} {...props} />;
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("text-[13px] font-medium tracking-[-0.01em] text-mist-100", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("mt-1 text-[11.5px] leading-relaxed text-mist-500", className)}
      {...props}
    />
  );
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="card-content" className={cn("p-5", className)} {...props} />;
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] px-5 py-3",
        className,
      )}
      {...props}
    />
  );
}

export { Card, CardContent, CardDescription, CardFooter, CardHeader, CardHeading, CardTitle };
