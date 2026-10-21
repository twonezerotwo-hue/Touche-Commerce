import {
  Activity,
  Banknote,
  FileText,
  Handshake,
  LayoutDashboard,
  Package,
  Settings,
  Sparkles,
  Truck,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  /** Visible label in the navigation rail. */
  label: string;
  icon: LucideIcon;
  /** Present once the module exists; absent means "planned". */
  href?: string;
  /** Stage in which the module becomes available. */
  stage: string;
}

/**
 * Navigation for the authenticated shell.
 *
 * Only routes that actually exist are links. Everything else renders as a
 * disabled placeholder with an explicit stage label — no dead links and no fake
 * screens.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Command Center", icon: LayoutDashboard, href: "/", stage: "Stage 0" },
  { label: "Account", icon: UserRound, href: "/account", stage: "Stage 1A" },
  { label: "Trade Workspace", icon: Handshake, stage: "Stage 2" },
  { label: "CRM", icon: Users, stage: "Stage 3" },
  { label: "RFQ & Quotes", icon: FileText, stage: "Stage 3" },
  { label: "Products", icon: Package, stage: "Stage 3" },
  { label: "Logistics", icon: Truck, stage: "Stage 3" },
  { label: "Finance", icon: Banknote, stage: "Stage 4" },
  { label: "AI Office", icon: Sparkles, stage: "Stage 5" },
  { label: "Settings", icon: Settings, stage: "Stage 1B" },
];

/** Public links outside the authenticated shell. */
export const PUBLIC_NAV_ITEMS: readonly NavItem[] = [
  { label: "System status", icon: Activity, href: "/status", stage: "Stage 0" },
];

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
