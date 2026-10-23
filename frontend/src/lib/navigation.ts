import {
  Activity,
  ArrowLeftRight,
  Banknote,
  Calculator,
  ChartNoAxesCombined,
  ClipboardCheck,
  FileText,
  FileWarning,
  FolderLock,
  Handshake,
  LayoutDashboard,
  Package,
  Receipt,
  ReceiptText,
  Scale,
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
  /** One line of context, used by the mobile navigation. */
  description: string;
}

export interface NavGroup {
  label: string;
  items: readonly NavItem[];
}

/**
 * Navigation for the authenticated shell.
 *
 * Only routes that actually exist are links. Everything else renders as a
 * disabled placeholder with an explicit stage label — no dead links and no fake
 * screens.
 */
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    label: "Trade core",
    items: [
      {
        label: "Command Center",
        icon: LayoutDashboard,
        href: "/",
        stage: "Stage 2",
        description: "Live pipeline, activity and platform health",
      },
      {
        label: "Deals",
        icon: Handshake,
        href: "/deals",
        stage: "Stage 2",
        description: "Every deal, status and transition history",
      },
      {
        label: "CRM",
        icon: Users,
        href: "/crm",
        stage: "Stage 2",
        description: "Customers and suppliers for this company",
      },
      {
        label: "Products",
        icon: Package,
        href: "/products",
        stage: "Stage 2",
        description: "Catalogue SKUs, units and indicative prices",
      },
    ],
  },
  {
    label: "Sourcing",
    items: [
      {
        label: "RFQs",
        icon: FileText,
        href: "/rfq",
        stage: "Stage 3",
        description: "Supplier requests, revisions and dispatch evidence",
      },
      {
        label: "Supplier quotes",
        icon: Receipt,
        href: "/quotes",
        stage: "Stage 3",
        description: "Received prices, revisions and withdrawals",
      },
      {
        label: "Pricing",
        icon: Calculator,
        href: "/pricing",
        stage: "Stage 3",
        description: "Deterministic landed cost and selling price",
      },
      {
        label: "Sales quotes",
        icon: Handshake,
        href: "/sales-quotes",
        stage: "Stage 3",
        description: "Customer quotations with an approval workflow",
      },
      {
        label: "FX snapshots",
        icon: ArrowLeftRight,
        href: "/fx-rates",
        stage: "Stage 3",
        description: "Sourced rates used by every conversion",
      },
    ],
  },
  {
    label: "Execution",
    items: [
      {
        label: "Sales orders",
        icon: ClipboardCheck,
        href: "/orders",
        stage: "Stage 4",
        description: "Won deals, frozen commercial terms and fulfilment progress",
      },
      {
        label: "Purchase orders",
        icon: ReceiptText,
        href: "/purchase-orders",
        stage: "Stage 4",
        description: "Supplier orders, approvals and recorded dispatch evidence",
      },
      {
        label: "Shipments",
        icon: Truck,
        href: "/shipments",
        stage: "Stage 4",
        description: "Planned movements, partial deliveries and milestones",
      },
      {
        label: "Documents",
        icon: FolderLock,
        href: "/documents",
        stage: "Stage 4",
        description: "Private trade documents, versions and verification",
      },
      {
        label: "Finance",
        icon: Banknote,
        href: "/finance",
        stage: "Stage 5D",
        description: "Read-only TOUCHE FINANCE ledger, accounts and aging",
      },
      {
        label: "Reconciliation",
        icon: Scale,
        href: "/finance/reconciliation",
        stage: "Stage 5D",
        description: "Evidence runs, deterministic variances and human review",
      },
      {
        label: "Discrepancies",
        icon: FileWarning,
        href: "/finance/discrepancies",
        stage: "Stage 5D",
        description: "Exception queue for missing or conflicting evidence",
      },
      {
        label: "Intelligence",
        icon: ChartNoAxesCombined,
        href: "/finance/intelligence",
        stage: "Stage 5E",
        description: "Order profitability, cost variance and evidence coverage",
      },
    ],
  },
  {
    label: "Account",
    items: [
      {
        label: "Profile & access",
        icon: UserRound,
        href: "/account",
        stage: "Stage 2",
        description: "Identity, memberships and session policy",
      },
      {
        label: "Settings",
        icon: Settings,
        stage: "Stage 2",
        description: "Company settings and administration",
      },
    ],
  },
  {
    label: "Roadmap",
    items: [
      {
        label: "AI Office",
        icon: Sparkles,
        stage: "Stage 6",
        description: "Scoped assistants with audited actions",
      },
    ],
  },
];

/** Flat list kept for consumers that only need the available routes. */
export const NAV_ITEMS: readonly NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

/** Public links outside the authenticated shell. */
export const PUBLIC_NAV_ITEMS: readonly NavItem[] = [
  {
    label: "System status",
    icon: Activity,
    href: "/status",
    stage: "Stage 0",
    description: "Liveness, readiness and contract probes",
  },
];

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export interface WorkspaceContext {
  section: string;
  page: string;
}

/**
 * Breadcrumb labels derived from the route tree. Detail routes get an explicit
 * label instead of leaking a UUID into the chrome.
 */
export function resolveWorkspaceContext(pathname: string): WorkspaceContext {
  if (pathname === "/") return { section: "Workspace", page: "Command Center" };
  if (pathname === "/deals/new") return { section: "Deals", page: "New deal" };
  if (pathname.startsWith("/deals/")) return { section: "Deals", page: "Deal detail" };
  if (pathname === "/deals") return { section: "Workspace", page: "Deals" };
  if (pathname === "/rfq/new") return { section: "Sourcing", page: "New RFQ" };
  if (pathname.startsWith("/rfq/")) return { section: "Sourcing", page: "RFQ detail" };
  if (pathname === "/rfq") return { section: "Sourcing", page: "RFQs" };
  if (pathname.startsWith("/quotes/"))
    return { section: "Sourcing", page: "Supplier quote detail" };
  if (pathname === "/quotes") return { section: "Sourcing", page: "Supplier quotes" };
  if (pathname.startsWith("/pricing/")) return { section: "Sourcing", page: "Pricing scenario" };
  if (pathname === "/pricing") return { section: "Sourcing", page: "Pricing" };
  if (pathname.startsWith("/sales-quotes/")) {
    return { section: "Sourcing", page: "Sales quote detail" };
  }
  if (pathname === "/sales-quotes") return { section: "Sourcing", page: "Sales quotes" };
  if (pathname === "/fx-rates") return { section: "Sourcing", page: "FX snapshots" };
  if (pathname === "/orders") return { section: "Execution", page: "Sales orders" };
  if (pathname.startsWith("/orders/")) return { section: "Execution", page: "Sales order" };
  if (pathname === "/purchase-orders") return { section: "Execution", page: "Purchase orders" };
  if (pathname.startsWith("/purchase-orders/"))
    return { section: "Execution", page: "Purchase order" };
  if (pathname === "/shipments/new") return { section: "Logistics", page: "Plan shipment" };
  if (pathname.startsWith("/shipments/")) return { section: "Logistics", page: "Shipment" };
  if (pathname === "/shipments") return { section: "Logistics", page: "Shipments" };
  if (pathname === "/documents") return { section: "Documents", page: "Trade documents" };
  if (pathname === "/finance") return { section: "Finance", page: "Finance" };
  if (pathname.startsWith("/finance/reconciliation/")) {
    return { section: "Finance", page: "Reconciliation run" };
  }
  if (pathname === "/finance/reconciliation") return { section: "Finance", page: "Reconciliation" };
  if (pathname === "/finance/discrepancies") return { section: "Finance", page: "Discrepancies" };
  if (pathname.startsWith("/finance/orders/")) return { section: "Finance", page: "Order finance" };
  if (pathname === "/finance/intelligence") return { section: "Finance", page: "Intelligence" };
  if (pathname === "/finance/intelligence/orders") {
    return { section: "Finance", page: "Order profitability" };
  }
  if (pathname.startsWith("/finance/intelligence/orders/")) {
    return { section: "Finance", page: "Order intelligence" };
  }
  if (pathname === "/finance/intelligence/exceptions") {
    return { section: "Finance", page: "Financial exceptions" };
  }
  if (pathname === "/crm") return { section: "Workspace", page: "CRM" };
  if (pathname === "/products") return { section: "Workspace", page: "Products" };
  if (pathname === "/account") return { section: "Account", page: "Profile & access" };
  if (pathname === "/select-company") return { section: "Account", page: "Select company" };
  return { section: "Workspace", page: "Workspace" };
}
