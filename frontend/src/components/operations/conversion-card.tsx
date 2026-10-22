"use client";

import { useState } from "react";

import { OrderConversionPanel } from "@/components/operations/order-conversion";
import type { CustomerAcceptance, SalesQuoteOption } from "@/lib/operations/types";

/** Holds the commercial-model choice for the conversion panel. */
export function ConversionCard({
  dealId,
  quotes,
  acceptances,
  csrfToken,
  canWrite,
}: {
  dealId: string;
  quotes: SalesQuoteOption[];
  acceptances: CustomerAcceptance[];
  csrfToken: string;
  canWrite: boolean;
}) {
  const [brokerage, setBrokerage] = useState(false);
  return (
    <OrderConversionPanel
      dealId={dealId}
      quotes={quotes}
      acceptances={acceptances}
      csrfToken={csrfToken}
      canWrite={canWrite}
      brokerage={brokerage}
      onBrokerageChange={setBrokerage}
    />
  );
}
