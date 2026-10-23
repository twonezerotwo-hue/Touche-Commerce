import type { ReactNode } from "react";

import { isNegative } from "@/lib/finance/intelligence";

/**
 * Tints a profit or margin below zero so a loss does not read like a gain. The minus
 * sign stays in the text; colour only reinforces it. Not for cost variance: there a
 * negative number is a saving against the estimate.
 */
export function Signed({
  value,
  children,
}: {
  value: string | null | undefined;
  children: ReactNode;
}) {
  return isNegative(value) ? (
    <span className="text-crimson-400" data-negative>
      {children}
    </span>
  ) : (
    <>{children}</>
  );
}
