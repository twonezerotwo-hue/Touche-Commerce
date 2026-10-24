import type { MessageKey } from "./messages";

type TFn = (key: MessageKey) => string;

const RECORD_STATUS: Record<string, MessageKey> = {
  active: "statusActive",
  archived: "statusArchived",
  inactive: "statusInactive",
};

const COUNTERPARTY_TYPE: Record<string, MessageKey> = {
  buyer: "typeBuyer",
  supplier: "typeSupplier",
  both: "typeBoth",
};

/** Words the API stores in English ("active", "buyer"), shown in the reader's language. */
export function recordStatusLabel(t: TFn, status: string): string {
  const key = RECORD_STATUS[status];
  return key ? t(key) : status;
}

export function counterpartyTypeLabel(t: TFn, type: string): string {
  const key = COUNTERPARTY_TYPE[type];
  return key ? t(key) : type;
}

const DEAL_STATUS: Record<string, MessageKey> = {
  DRAFT: "dealStatusDraft",
  OPEN: "dealStatusOpen",
  NEGOTIATION: "dealStatusNegotiation",
  WON: "dealStatusWon",
  LOST: "dealStatusLost",
  CANCELLED: "dealStatusCancelled",
};

/** Deal status codes ("OPEN") in the reader's language; unknown codes are shown as they are. */
export function dealStatusLabel(t: TFn, status: string): string {
  const key = DEAL_STATUS[status];
  return key ? t(key) : status;
}
