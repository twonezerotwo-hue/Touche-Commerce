import {
  Banknote,
  FileText,
  Handshake,
  LayoutDashboard,
  Package,
  Settings,
  Sparkles,
  Truck,
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
 * Navigation placeholders for the Stage 0 shell.
 *
 * Only Command Center is implemented. Everything else renders as a disabled
 * placeholder with an explicit stage label — no dead links and no fake screens.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Command Center", icon: LayoutDashboard, href: "/", stage: "Stage 0" },
  { label: "Trade Workspace", icon: Handshake, stage: "Stage 2" },
  { label: "CRM", icon: Users, stage: "Stage 3" },
  { label: "RFQ & Quotes", icon: FileText, stage: "Stage 3" },
  { label: "Products", icon: Package, stage: "Stage 3" },
  { label: "Logistics", icon: Truck, stage: "Stage 3" },
  { label: "Finance", icon: Banknote, stage: "Stage 4" },
  { label: "AI Office", icon: Sparkles, stage: "Stage 5" },
  { label: "Settings", icon: Settings, stage: "Stage 1A" },
];
