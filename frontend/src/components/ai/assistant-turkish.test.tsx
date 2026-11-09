import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnswerView } from "./answer-view";
import { ProposalCard } from "./proposal-card";
import { RunProgress } from "./run-progress";
import { ActivityList, ProviderStatusCard, ToolRegistryPanel } from "./side-panels";
import { CommunicationPreflight } from "@/components/communications/preflight";
import { SuppressionPanel } from "@/components/communications/suppression-panel";
import {
  basisLabels,
  describeErrorIn,
  describeWarningIn,
  draftKindLabel,
  formatUsdIn,
  priorityLabel,
} from "@/lib/ai/format";
import type { AiMessage, AiProposal, AiRun, AiStatus, AiToolList } from "@/lib/ai/types";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { translate } from "@/lib/i18n/messages";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/ai/client");

afterEach(() => {
  vi.unstubAllGlobals();
});

const inTurkish = (ui: React.ReactElement) =>
  render(<LocaleProvider initialLocale="tr">{ui}</LocaleProvider>);
const tTr = (key: Parameters<typeof translate>[1], params?: Record<string, string | number>) =>
  translate("tr", key, params);

const status = {
  enabled: true,
  mode: "MOCK",
  provider: "mock",
  model: "mock-trade-director-1",
  external_processing: true,
  prompt_version: "trade_director@1.0.0",
  limits: { max_tool_calls_per_request: 10 },
  usage: {
    tokens_today: 12000,
    cost_usd_today: "0.500000",
    runs_today: 3,
    daily_token_budget: 500000,
    daily_cost_budget_usd: "5.00",
  },
  notice: "Offline test provider.",
} as unknown as AiStatus;

const message = (structured: Partial<NonNullable<AiMessage["structured"]>>): AiMessage =>
  ({
    id: "m1",
    role: "ASSISTANT",
    content: "plain",
    evidence: [],
    structured: {
      summary: "Two quotes compared.",
      warnings: [],
      findings: [],
      recommendations: [],
      missing_inputs: [],
      drafts: [],
      task_proposals: [],
      ...structured,
    },
  }) as unknown as AiMessage;

const proposal = (overrides: Partial<AiProposal> = {}): AiProposal =>
  ({
    id: "p1",
    kind: "DRAFT",
    status: "PROPOSED",
    title: "Follow up with the supplier",
    payload: { kind: "SUPPLIER_FOLLOW_UP", title: "Follow up", body: "Dear supplier, ..." },
    warnings: ["UNVERIFIED_NUMBER"],
    evidence: [],
    edited: false,
    effect_summary: "Nothing is sent.",
    decided_at: null,
    decision_notes: null,
    version: 1,
    ...overrides,
  }) as unknown as AiProposal;

describe("assistant words", () => {
  it("translates evidence bases, errors, warnings, draft kinds and priorities", () => {
    expect(basisLabels(tTr, "AI_INFERENCE").label).toBe("Yapay zekâ çıkarımı");
    expect(basisLabels(tTr, "CONFIRMED_SOURCE").label).toBe("Doğrulanmış kaynak");
    expect(describeErrorIn(tTr, "AI_BUDGET_EXCEEDED")).toContain("bütçesine ulaşıldı");
    expect(describeErrorIn(tTr, "SOMETHING_ELSE", "Server said no")).toBe("Server said no");
    expect(describeErrorIn(tTr, null)).toBe("İstek tamamlanamadı.");
    expect(describeWarningIn(tTr, "UNVERIFIED_NUMBER")).toContain("Doğrulanmamış sayın");
    expect(describeWarningIn(tTr, "NEW_WARNING")).toBe("new warning");
    expect(draftKindLabel(tTr, "RFQ_EMAIL")).toBe("RFQ e-postası");
    expect(priorityLabel(tTr, "HIGH")).toBe("yüksek");
  });

  it("formats the cost with the reader's separators", () => {
    expect(formatUsdIn("0.5", "en")).toBe("$0.50");
    expect(formatUsdIn("0.5", "tr")).toBe("$0,50");
    expect(formatUsdIn("0.001", "tr")).toBe("<$0.01");
  });
});

describe("AI Office panels in Turkish", () => {
  it("shows the provider card, its budget and the safety promises", () => {
    inTurkish(<ProviderStatusCard status={status} companyName="Acme" />);
    expect(screen.getByText("Çevrimdışı test sağlayıcısı")).toBeInTheDocument();
    expect(screen.getByText("Dış işleme")).toBeInTheDocument();
    expect(screen.getByText("3 istek · $0,50 / $5,00")).toBeInTheDocument();
    expect(screen.getByText("Kayıtlara salt okunur erişim")).toBeInTheDocument();
    expect(screen.getByText(/Hiçbir zaman göndermez, imzalamaz/)).toBeInTheDocument();
  });

  it("lists the tools, the approval classes and the actions that are never available", () => {
    const tools = {
      tools: [
        {
          name: "list_active_deals",
          description: "List open deals.",
          tool_class: "READ_ONLY",
          permission: "company.view",
          available: false,
          parameters: {},
        },
      ],
      blocked_actions: [{ name: "send_email", reason: "Sending needs a person." }],
      classes: [{ name: "READ_ONLY", description: "Reads existing records." }],
    } as unknown as AiToolList;
    inTurkish(<ToolRegistryPanel tools={tools} />);
    expect(screen.getByText("Salt okunur araçlar")).toBeInTheDocument();
    expect(screen.getByText("Yetki yok")).toBeInTheDocument();
    expect(screen.getByText("Hiçbir zaman kullanılamaz")).toBeInTheDocument();
  });

  it("says there is no activity yet", () => {
    inTurkish(<ActivityList runs={[]} />);
    expect(screen.getByText("Bu şirkette henüz yapay zekâ isteği yok.")).toBeInTheDocument();
  });

  it("shows a running request, its tool calls and the cancel button", () => {
    const run = {
      id: "r1",
      status: "RUNNING",
      tool_calls: [
        {
          ordinal: 1,
          tool_name: "list_active_deals",
          status: "OK",
          duration_ms: 12,
          tool_class: "READ_ONLY",
        },
      ],
      safety_flags: [],
      provider: "mock",
      model: "m",
      input_tokens: 10,
      output_tokens: 5,
      model_steps: 2,
    } as unknown as AiRun;
    inTurkish(<RunProgress run={run} onCancel={() => undefined} />);
    expect(screen.getByText("Kayıtlarınız okunuyor…")).toBeInTheDocument();
    expect(screen.getByText("Çalışıyor")).toBeInTheDocument();
    expect(screen.getByText("Okundu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vazgeç" })).toBeInTheDocument();
    expect(screen.getByText(/15 jeton · 2 adım/)).toBeInTheDocument();
  });
});

describe("the answer and its proposals in Turkish", () => {
  it("keeps the evidence label on every finding and says what was proposed", () => {
    inTurkish(
      <AnswerView
        message={message({
          findings: [
            {
              claim: "Supplier B is cheaper.",
              basis: "AI_INFERENCE",
              figures: [],
              evidence: [],
              warnings: [],
            } as never,
          ],
          recommendations: [
            {
              action: "Ask for a revision",
              priority: "HIGH",
              rationale: "",
              evidence: [],
            } as never,
          ],
          drafts: [{} as never],
        })}
      />,
    );
    expect(screen.getByText("Bulgular")).toBeInTheDocument();
    expect(screen.getByText("Yapay zekâ çıkarımı")).toBeInTheDocument();
    expect(screen.getByText("yüksek")).toBeInTheDocument();
    expect(screen.getByText(/1 taslak ve 0 görev önerildi/)).toBeInTheDocument();
    expect(screen.getByText("Önerilen işlemler")).toBeInTheDocument();
    expect(screen.getByText(/Alıntılanan kayıtlı bir veri yok/)).toBeInTheDocument();
  });

  it("will not approve a draft with unverified figures until a person has reviewed them", async () => {
    const user = userEvent.setup();
    inTurkish(
      <ProposalCard proposal={proposal()} csrfToken="c" canDecide onChanged={() => undefined} />,
    );
    expect(screen.getByText("Tedarikçi takibi")).toBeInTheDocument();
    expect(screen.getByText("Bir kişiyi bekliyor")).toBeInTheDocument();
    expect(screen.getByText("Önizleme — gönderilmedi")).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: "Metni onayla" });
    expect(approve).toBeDisabled();
    await user.click(screen.getByLabelText("Bu metindeki doğrulanmamış rakamları inceledim."));
    expect(approve).toBeEnabled();
  });

  it("only lets a role with approval rights decide", () => {
    inTurkish(
      <ProposalCard
        proposal={proposal()}
        csrfToken="c"
        canDecide={false}
        onChanged={() => undefined}
      />,
    );
    expect(
      screen.getByText(
        "Rolünüz önerileri okuyabilir ancak onaylayamaz, düzenleyemez veya reddedemez.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Metni onayla" })).toBeNull();
  });

  it("shows a decided proposal with who decided it, in Turkish", () => {
    inTurkish(
      <ProposalCard
        proposal={proposal({
          status: "APPROVED",
          decided_at: "2026-10-22T09:00:00Z",
          decision_notes: "Looks fine",
        })}
        csrfToken="c"
        canDecide
        onChanged={() => undefined}
      />,
    );
    expect(
      screen.getByText(/Bir kişi tarafından onaylandı \(2026-10-22\) — “Looks fine”\./),
    ).toBeInTheDocument();
  });
});

describe("communications in Turkish stay draft-only", () => {
  it("explains the blockers of a readiness check without sending anything", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        sendable: false,
        external_sending_enabled: false,
        blockers: ["DRAFT_NOT_APPROVED", "CONSENT_UNDOCUMENTED", "SOMETHING_NEW"],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    inTurkish(
      <CommunicationPreflight
        draftId="d1"
        draftVersion={1}
        csrfToken="c"
        counterparties={[{ id: "c1", name: "Buyer Ltd" }]}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Hazırlığı kontrol et (gönderim yok)" }));
    expect(screen.getByLabelText("CRM karşı tarafı (kaynak)")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Alıcı (saklanmaz)"), "buyer@example.com");
    await user.click(screen.getByRole("button", { name: "Engelleri kontrol et" }));
    expect(await screen.findByText("Gönderim engellendi")).toBeInTheDocument();
    expect(
      screen.getByText("Önce bir kişinin bu taslağı incelemesi ve onaylaması gerekir."),
    ).toBeInTheDocument();
    expect(screen.getByText("Çözülmemiş bir teslimat gereksinimi var.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("makes the do-not-contact record deliberate", async () => {
    const user = userEvent.setup();
    inTurkish(
      <SuppressionPanel
        csrfToken="c"
        counterparties={[{ id: "c1", name: "Buyer Ltd" }]}
        saved={[{ id: "s1", counterparty_id: "c1", channel: "EMAIL", reason: "CONTACT_REQUEST" }]}
      />,
    );
    expect(screen.getByText("Rahatsız etme listesi")).toBeInTheDocument();
    const record = screen.getByRole("button", { name: "Kalıcı engellemeyi kaydet" });
    expect(record).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("CRM karşı tarafı"), "c1");
    expect(record).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(record).toBeEnabled();
    const [row] = screen.getAllByRole("listitem");
    expect(row).toHaveTextContent("ENGELLENDİ");
    expect(row).toHaveTextContent("EMAIL");
  });
});
