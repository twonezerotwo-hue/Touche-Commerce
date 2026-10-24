import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { RfqForm } from "@/components/sourcing/rfq-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { serverGet } from "@/lib/api/server";
import { loadSession } from "@/lib/auth/session";
import { getServerT, titleFor } from "@/lib/i18n/server";
import type { CounterpartyList, DealList, ProductList } from "@/lib/trade/types";

export const dynamic = "force-dynamic";
export const generateMetadata = () => titleFor("rfqNew");

export default async function NewRfqPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const { t } = await getServerT();

  const session = state.session.session;
  const canWrite = session.company?.permissions.includes("trade.write") ?? false;

  if (!canWrite) {
    return (
      <div className="mx-auto max-w-[900px] space-y-4">
        <PageHeader
          eyebrow={t("rfqNewEyebrow")}
          back={{ href: "/rfq", label: t("rfqPageTitle") }}
          title={t("readOnlyAccess")}
          description={t("rfqReadOnlyBody")}
        />
        <Alert variant="info" title={t("readOnlyAccess")}>
          {t("rfqReadOnlyAlert")}
        </Alert>
      </div>
    );
  }

  const [deals, counterparties, products] = await Promise.all([
    serverGet<DealList>("/deals?limit=100"),
    serverGet<CounterpartyList>("/counterparties?limit=100&status=active"),
    serverGet<ProductList>("/products?limit=100&status=active"),
  ]);

  const failure = !deals.ok
    ? deals
    : !counterparties.ok
      ? counterparties
      : !products.ok
        ? products
        : null;
  const suppliers = counterparties.ok
    ? counterparties.data.items.filter((item) => item.type !== "buyer")
    : [];

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <PageHeader
        eyebrow={t("rfqNewEyebrow")}
        back={{ href: "/rfq", label: t("rfqPageTitle") }}
        meta={<Badge variant="secondary">{t("srcStDraft")}</Badge>}
        title={t("rfqNewTitle")}
        description={t("rfqNewDescription")}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href="/rfq">
              <ArrowLeft className="size-3.5" aria-hidden />
              {t("actionCancel")}
            </Link>
          </Button>
        }
      />

      {failure ? (
        <Alert variant="danger" title={t("rfqMasterDataUnavailable")}>
          {failure.message}
        </Alert>
      ) : (
        <RfqForm
          deals={deals.ok ? deals.data.items : []}
          suppliers={suppliers}
          products={products.ok ? products.data.items : []}
          csrfToken={session.csrf_token}
          defaultCurrency={session.company?.default_currency ?? "USD"}
        />
      )}
    </div>
  );
}
