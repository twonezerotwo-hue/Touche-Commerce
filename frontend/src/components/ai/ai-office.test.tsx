import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiOffice, type AiOfficeProps } from "./ai-office";
import { ProposalCard } from "./proposal-card";
import type { AiResult } from "@/lib/ai/client";
import * as client from "@/lib/ai/client";
import type {
  AiConversation,
  AiConversationDetail,
  AiEvidence,
  AiMessage,
  AiProposal,
  AiRun,
  AiStatus,
  AiToolList,
} from "@/lib/ai/types";

vi.mock("@/lib/ai/client");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const mocked = vi.mocked(client);

function ok<T>(data: T): AiResult<T> {
  return { ok: true, data, etag: null };
}
function fail<T>(code: string, message = "Failed"): AiResult<T> {
  return { ok: false, code, message, requestId: "req-1" };
}

const status: AiStatus = {
  enabled: true,
  mode: "MOCK",
  provider: "mock",
  model: "mock-trade-director-1",
  external_processing: false,
  prompt_version: "trade_director@1.0.0",
  limits: {
    max_model_steps: 6,
    max_tool_calls_per_request: 10,
    max_output_tokens: 1500,
    max_request_tokens: 40000,
    max_user_message_chars: 4000,
    max_tool_result_chars: 12000,
    max_concurrent_runs: 4,
    max_runs_per_user_per_minute: 6,
    request_timeout_seconds: 30,
    run_deadline_seconds: 120,
  },
  usage: {
    tokens_today: 12000,
    cost_usd_today: "0.000000",
    runs_today: 3,
    daily_token_budget: 500000,
    daily_cost_budget_usd: "5.00",
  },
  notice: "Answers come from a deterministic offline test provider, not a language model.",
  can_approve: true,
  read_only_tools: true,
  accounting_writes_enabled: false,
  sends_messages: false,
};

const tools: AiToolList = {
  tools: [
    {
      name: "list_active_deals",
      description: "List open deals.",
      tool_class: "READ_ONLY",
      permission: "company.view",
      available: true,
      parameters: {},
    },
  ],
  blocked_actions: [{ name: "send_email", reason: "Sending messages needs a person." }],
  classes: [{ name: "READ_ONLY", description: "Reads existing records." }],
};

const conversation: AiConversation = {
  id: "conv-1",
  title: "Analyse my active deals",
  status: "ACTIVE",
  prompt_version: "trade_director@1.0.0",
  created_at: "2026-10-23T09:00:00Z",
  updated_at: "2026-10-23T09:05:00Z",
  version: 3,
};

const evidence: AiEvidence = {
  id: "E1",
  entity_type: "DEAL",
  entity_id: "deal-1",
  reference: "DL-0001",
  label: "OPEN deal with Buyer Ltd",
  basis: "CONFIRMED_SOURCE",
  as_of: "2026-10-23T08:00:00+00:00",
  completeness: "COMPLETE",
  facts: { total_value: "250.00", currency: "USD" },
  warnings: [],
  tool: "list_active_deals",
  href: "/deals/deal-1",
};

const answer: AiMessage = {
  id: "msg-2",
  role: "ASSISTANT",
  content: "Reviewed 1 recorded source.",
  run_id: "run-1",
  created_at: "2026-10-23T09:05:00Z",
  evidence: [
    evidence,
    {
      ...evidence,
      id: "E2",
      entity_type: "PRICING_SCENARIO",
      entity_id: "scn-1",
      reference: "Scenario DL-0001",
      basis: "ESTIMATED",
      href: "/pricing/scn-1",
      tool: "get_pricing_scenario",
    },
  ],
  structured: {
    summary: "One deal needs attention.",
    findings: [
      {
        claim: "DL-0001 is open and worth 250.00 USD.",
        basis: "CONFIRMED_SOURCE",
        evidence: ["E1"],
        figures: [{ label: "total value", value: "250.00", currency: "USD", evidence: "E1" }],
        warnings: [],
      },
      {
        claim: "The margin is probably healthy.",
        basis: "AI_INFERENCE",
        evidence: [],
        figures: [],
        warnings: ["NO_SOURCE_EVIDENCE"],
      },
      {
        claim: "Landed cost is an estimate.",
        basis: "ESTIMATED",
        evidence: ["E2"],
        figures: [],
        warnings: [],
      },
    ],
    recommendations: [
      {
        action: "Request a revised quote.",
        priority: "HIGH",
        rationale: "The quote expires soon.",
        evidence: ["E1"],
        warnings: [],
      },
    ],
    missing_inputs: [{ item: "DL-0001: freight cost not recorded", evidence: ["E1"] }],
    drafts: [
      { kind: "SUPPLIER_FOLLOW_UP", title: "Chase", body: "Hello", evidence: ["E1"], warnings: [] },
    ],
    task_proposals: [],
    warnings: ["UNVERIFIED_NUMBER"],
  },
};

const userMessage: AiMessage = {
  id: "msg-1",
  role: "USER",
  content: "Analyse my active deals",
  run_id: "run-1",
  created_at: "2026-10-23T09:04:00Z",
  evidence: [],
  structured: null,
};

const detail: AiConversationDetail = {
  conversation,
  messages: [userMessage, answer],
  proposals: [],
};

function run(overrides: Partial<AiRun> = {}): AiRun {
  return {
    id: "run-1",
    conversation_id: "conv-1",
    conversation_title: "Analyse my active deals",
    status: "RUNNING",
    provider: "mock",
    model: "mock-trade-director-1",
    prompt_version: "trade_director@1.0.0",
    is_external: false,
    input_tokens: 0,
    output_tokens: 0,
    estimated_usage: false,
    cost_usd: "0.000000",
    model_steps: 0,
    tool_call_count: 0,
    provider_calls: 0,
    error_code: null,
    validation_warnings: [],
    safety_flags: [],
    started_at: "2026-10-23T09:04:00Z",
    finished_at: null,
    tool_calls: [],
    message: null,
    proposals: [],
    ...overrides,
  };
}

function proposal(overrides: Partial<AiProposal> = {}): AiProposal {
  return {
    id: "prop-1",
    conversation_id: "conv-1",
    run_id: "run-1",
    kind: "DRAFT",
    action_type: "DRAFT_REVIEW",
    action_class: "DRAFT_PROPOSAL",
    title: "Supplier follow-up",
    payload: {
      kind: "SUPPLIER_FOLLOW_UP",
      title: "Supplier follow-up",
      body: "Hello supplier,\nplease confirm.",
    },
    edited: false,
    evidence: [evidence],
    warnings: [],
    status: "PROPOSED",
    created_by: "user-1",
    decided_by: null,
    decided_at: null,
    decision_notes: null,
    execution_result: null,
    effect_summary: "Approving records that a person reviewed this wording. Nothing is sent.",
    created_at: "2026-10-23T09:05:00Z",
    updated_at: "2026-10-23T09:05:00Z",
    version: 1,
    ...overrides,
  };
}

function props(overrides: Partial<AiOfficeProps> = {}): AiOfficeProps {
  return {
    companyName: "Meridian Commodities",
    csrfToken: "csrf-token",
    status,
    tools,
    suggestions: [
      { id: "deals", title: "Analyse active deals", prompt: "Analyse my active deals." },
    ],
    conversations: [conversation],
    proposals: [],
    activity: [],
    pollIntervalMs: 5,
    ...overrides,
  };
}

beforeEach(() => {
  mocked.loadProposals.mockResolvedValue(ok({ items: [] }));
  mocked.loadActivity.mockResolvedValue(ok({ items: [] }));
});

describe("conversation and answers", () => {
  it("loads a past conversation and shows basis labels and source links", async () => {
    mocked.loadConversation.mockResolvedValue(ok(detail));
    render(<AiOffice {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: /Analyse my active deals/ }));

    const answerBlock = await screen.findByRole("article", { name: "Trade Director answer" });
    expect(within(answerBlock).getByText("One deal needs attention.")).toBeInTheDocument();

    // Each claim carries exactly its basis; inference is visibly different from fact.
    expect(within(answerBlock).getAllByText("Confirmed source").length).toBeGreaterThan(0);
    expect(within(answerBlock).getAllByText("AI inference").length).toBeGreaterThan(0);
    expect(within(answerBlock).getAllByText("Estimated").length).toBeGreaterThan(0);

    // Figures come from the evidence, with their currency.
    expect(within(answerBlock).getByText("250.00 USD")).toBeInTheDocument();

    // Evidence navigates to the record in the application.
    const link = within(answerBlock).getAllByRole("link", { name: /Open DL-0001/ })[0];
    expect(link).toHaveAttribute("href", "/deals/deal-1");

    // Server-side validation findings are explained, not hidden.
    expect(within(answerBlock).getByText(/did not come from any record/)).toBeInTheDocument();
    expect(within(answerBlock).getByText(/No stored record supports this/)).toBeInTheDocument();
    expect(within(answerBlock).getByText(/Nothing is sent or changed until/)).toBeInTheDocument();
  });

  it("never links an evidence href that leaves the application", async () => {
    const hostile: AiMessage = {
      ...answer,
      evidence: [
        { ...evidence, href: "https://evil.example/steal" },
        { ...evidence, id: "E2", href: "//evil.example" },
      ],
      structured: {
        ...answer.structured!,
        findings: [{ ...answer.structured!.findings[0], evidence: ["E1", "E2"] }],
      },
    };
    mocked.loadConversation.mockResolvedValue(ok({ ...detail, messages: [userMessage, hostile] }));
    render(<AiOffice {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: /Analyse my active deals/ }));
    const block = await screen.findByRole("article", { name: "Trade Director answer" });
    expect(within(block).queryByRole("link", { name: /Open DL-0001/ })).not.toBeInTheDocument();
    expect(block.querySelector("a[href^='http'], a[href^='//']")).toBeNull();
  });

  it("shows the empty state with suggestions and fills the composer from one", async () => {
    render(<AiOffice {...props({ conversations: [] })} />);
    expect(screen.getByText("Ask the Trade Director", { selector: "p" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Analyse active deals" }));
    expect(screen.getByLabelText("Ask the Trade Director")).toHaveValue("Analyse my active deals.");
  });

  it("shows loading and error states for history", async () => {
    let release: (value: AiResult<AiConversationDetail>) => void = () => undefined;
    mocked.loadConversation.mockReturnValue(new Promise((resolve) => (release = resolve)));
    render(<AiOffice {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: /Analyse my active deals/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Loading conversation");
    release(fail("NOT_FOUND", "The conversation does not exist."));
    expect(await screen.findByText("The conversation does not exist.")).toBeInTheDocument();
  });
});

describe("asking a question", () => {
  it("creates a conversation, shows tool progress, then the checked answer", async () => {
    mocked.createConversation.mockResolvedValue(ok(conversation));
    mocked.sendMessage.mockResolvedValue(ok({ run: run(), message: userMessage }));
    const readDeals = {
      ordinal: 1,
      tool_name: "list_active_deals",
      tool_class: "READ_ONLY" as const,
      status: "OK" as const,
      arguments: {},
      evidence_ids: ["E1"],
      result_chars: 500,
      duration_ms: 12,
      error_code: null,
      created_at: "2026-10-23T09:04:01Z",
    };
    mocked.loadRun
      .mockResolvedValueOnce(ok(run({ tool_call_count: 1, tool_calls: [readDeals] })))
      .mockResolvedValue(
        ok(
          run({
            status: "COMPLETED",
            model_steps: 2,
            input_tokens: 900,
            output_tokens: 100,
            tool_call_count: 1,
            tool_calls: [readDeals],
          }),
        ),
      );
    mocked.loadConversation.mockResolvedValue(ok(detail));

    render(<AiOffice {...props({ conversations: [] })} />);
    await userEvent.type(
      screen.getByLabelText("Ask the Trade Director"),
      "Analyse my active deals",
    );
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(mocked.createConversation).toHaveBeenCalledWith("csrf-token");
    expect(mocked.sendMessage).toHaveBeenCalledWith(
      "conv-1",
      "Analyse my active deals",
      "csrf-token",
    );

    const progress = await screen.findByRole("region", { name: "Tool execution" });
    expect(progress).toBeInTheDocument();
    expect(await screen.findByText("List active deals")).toBeInTheDocument();

    expect(
      await screen.findByRole("article", { name: "Trade Director answer" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Tool execution" })).toHaveAttribute(
        "data-run-status",
        "COMPLETED",
      ),
    );
    expect(screen.getByText(/1000 tokens/)).toBeInTheDocument();
    expect(mocked.loadActivity).toHaveBeenCalled();
    expect(mocked.loadProposals).toHaveBeenCalled();
  });

  it("explains a provider outage without inventing an answer", async () => {
    mocked.createConversation.mockResolvedValue(ok(conversation));
    mocked.sendMessage.mockResolvedValue(ok({ run: run(), message: userMessage }));
    mocked.loadRun.mockResolvedValue(
      ok(run({ status: "FAILED", error_code: "AI_PROVIDER_UNAVAILABLE" })),
    );
    mocked.loadConversation.mockResolvedValue(
      ok({ conversation, messages: [userMessage], proposals: [] }),
    );
    render(<AiOffice {...props({ conversations: [] })} />);
    await userEvent.type(screen.getByLabelText("Ask the Trade Director"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/provider is unavailable right now/)).toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Trade Director answer" }),
    ).not.toBeInTheDocument();
  });

  it("shows a server refusal such as the rate limit", async () => {
    mocked.createConversation.mockResolvedValue(ok(conversation));
    mocked.sendMessage.mockResolvedValue(fail("AI_TOO_MANY_RUNS"));
    render(<AiOffice {...props({ conversations: [] })} />);
    await userEvent.type(screen.getByLabelText("Ask the Trade Director"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/Too many AI requests are running/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the Trade Director")).toHaveValue("hello");
  });

  it("lets the operator cancel a running request", async () => {
    mocked.createConversation.mockResolvedValue(ok(conversation));
    mocked.sendMessage.mockResolvedValue(ok({ run: run(), message: userMessage }));
    mocked.loadRun.mockResolvedValue(ok(run()));
    mocked.cancelRun.mockResolvedValue(ok(run()));
    render(<AiOffice {...props({ conversations: [], pollIntervalMs: 50 })} />);
    await userEvent.type(screen.getByLabelText("Ask the Trade Director"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(mocked.cancelRun).toHaveBeenCalledWith("run-1", "csrf-token");
  });

  it("surfaces withheld instruction-like text as a safety note", async () => {
    mocked.createConversation.mockResolvedValue(ok(conversation));
    mocked.sendMessage.mockResolvedValue(ok({ run: run(), message: userMessage }));
    mocked.loadRun.mockResolvedValue(
      ok(
        run({
          status: "COMPLETED",
          safety_flags: ["INJECTION:INSTRUCTION_OVERRIDE", "BLOCKED_TOOL_REQUESTED"],
          tool_calls: [
            {
              ordinal: 1,
              tool_name: "send_email",
              tool_class: "BLOCKED",
              status: "DENIED",
              arguments: {},
              evidence_ids: [],
              result_chars: 90,
              duration_ms: 1,
              error_code: "TOOL_BLOCKED",
              created_at: "2026-10-23T09:04:01Z",
            },
          ],
        }),
      ),
    );
    mocked.loadConversation.mockResolvedValue(ok(detail));
    render(<AiOffice {...props({ conversations: [] })} />);
    await userEvent.type(screen.getByLabelText("Ask the Trade Director"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(/Instruction-like text found in records was withheld/),
    ).toBeInTheDocument();
    expect(screen.getByText("Denied")).toBeInTheDocument();
    expect(screen.getByLabelText("Blocked action")).toBeInTheDocument();
  });
});

describe("provider unavailable", () => {
  it("disables the composer and explains why, but keeps history reachable", async () => {
    mocked.loadConversation.mockResolvedValue(ok(detail));
    const disabled: AiStatus = {
      ...status,
      enabled: false,
      mode: "DISABLED",
      provider: null,
      model: null,
      notice: "The AI Office is disabled for this deployment.",
    };
    render(<AiOffice {...props({ status: disabled })} />);
    expect(screen.getByText("AI Office is unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the Trade Director")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /Analyse my active deals/ }));
    expect(
      await screen.findByRole("article", { name: "Trade Director answer" }),
    ).toBeInTheDocument();
  });

  it("flags external processing when a real provider is configured", () => {
    render(
      <AiOffice
        {...props({
          status: {
            ...status,
            mode: "REAL",
            provider: "openai_compatible",
            external_processing: true,
          },
        })}
      />,
    );
    expect(screen.getByText("External processing")).toBeInTheDocument();
    expect(screen.getByText("Live provider")).toBeInTheDocument();
  });
});

describe("proposals and permissions", () => {
  it("previews a draft as not sent and lets an authorised person approve it", async () => {
    const pending = proposal();
    const approved = proposal({
      status: "APPROVED",
      version: 2,
      decided_at: "2026-10-23T10:00:00Z",
      decision_notes: "ok",
    });
    mocked.decideProposal.mockResolvedValue(ok(approved));
    render(<AiOffice {...props({ proposals: [pending] })} />);

    const card = screen.getByRole("article", { name: /Draft: Supplier follow-up/ });
    expect(within(card).getByText(/Preview — not sent/)).toBeInTheDocument();
    expect(within(card).getByText(/Hello supplier/)).toBeInTheDocument();
    expect(within(card).getByText(/Nothing is sent/)).toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: /Approve wording/ }));
    expect(mocked.decideProposal).toHaveBeenCalledWith(
      pending,
      "approve",
      { notes: "", acknowledgeWarnings: false },
      "csrf-token",
    );
    expect(await screen.findByText(/Approved by a person/)).toBeInTheDocument();
  });

  it("hides approve, edit and reject from a role that cannot decide", () => {
    render(
      <AiOffice
        {...props({ status: { ...status, can_approve: false }, proposals: [proposal()] })}
      />,
    );
    const card = screen.getByRole("article", { name: /Draft: Supplier follow-up/ });
    expect(within(card).queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(within(card).getByText(/cannot approve, edit or reject/)).toBeInTheDocument();
  });

  it("requires acknowledging unverified figures before approval", async () => {
    mocked.decideProposal.mockResolvedValue(ok(proposal({ status: "APPROVED", version: 2 })));
    const risky = proposal({ warnings: ["UNVERIFIED_NUMBER"] });
    render(<ProposalCard proposal={risky} csrfToken="t" canDecide onChanged={() => undefined} />);
    const approve = screen.getByRole("button", { name: /Approve wording/ });
    expect(approve).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/reviewed the unverified figures/));
    expect(approve).toBeEnabled();
    await userEvent.click(approve);
    expect(mocked.decideProposal).toHaveBeenCalledWith(
      risky,
      "approve",
      { notes: "", acknowledgeWarnings: true },
      "t",
    );
  });

  it("edits the wording through the API and shows an error on a version conflict", async () => {
    mocked.editProposal.mockResolvedValueOnce(fail("VERSION_CONFLICT"));
    render(
      <ProposalCard proposal={proposal()} csrfToken="t" canDecide onChanged={() => undefined} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    await userEvent.clear(screen.getByLabelText("Draft text"));
    await userEvent.type(screen.getByLabelText("Draft text"), "New wording");
    await userEvent.click(screen.getByRole("button", { name: "Save wording" }));
    expect(mocked.editProposal).toHaveBeenCalledWith(
      expect.objectContaining({ id: "prop-1" }),
      { title: "Supplier follow-up", body: "New wording" },
      "t",
    );
    expect(await screen.findByText(/Someone changed this proposal/)).toBeInTheDocument();
  });

  it("shows a task proposal with its target and a decided state without actions", () => {
    const task = proposal({
      id: "prop-2",
      kind: "TASK",
      action_type: "OPERATOR_TASK",
      action_class: "REQUIRES_HUMAN_APPROVAL",
      title: "Complete missing inputs",
      payload: {
        title: "Complete missing inputs",
        rationale: "Freight missing.",
        priority: "HIGH",
        target: { entity_type: "DEAL", entity_id: "deal-1" },
      },
      status: "REJECTED",
      decided_at: "2026-10-23T10:00:00Z",
    });
    render(<ProposalCard proposal={task} csrfToken="t" canDecide onChanged={() => undefined} />);
    expect(screen.getByText("Suggested task")).toBeInTheDocument();
    expect(screen.getByText(/Refers to deal/)).toBeInTheDocument();
    expect(screen.getByText(/Rejected by a person/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
  });
});

describe("side panels and tenant switching", () => {
  beforeEach(() => {
    mocked.loadConversation.mockResolvedValue(ok(detail));
  });

  it("lists tools, approval classes and the actions that are never available", async () => {
    render(<AiOffice {...props()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Tools" }));
    expect(screen.getByText("List active deals")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
    expect(screen.getByText("send_email")).toBeInTheDocument();
    expect(screen.getByText("READ_ONLY", { selector: "span" })).toBeInTheDocument();
  });

  it("shows activity history with usage", async () => {
    render(
      <AiOffice
        {...props({
          activity: [
            run({
              status: "COMPLETED",
              tool_call_count: 3,
              input_tokens: 2000,
              output_tokens: 500,
            }),
            run({ id: "run-0", status: "FAILED", error_code: "AI_BUDGET_EXCEEDED" }),
          ],
        })}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "Activity" }));
    const list = screen.getByRole("list", { name: "Activity history" });
    expect(within(list).getByText(/3 tool calls/)).toBeInTheDocument();
    expect(within(list).getByText(/usage budget was reached/)).toBeInTheDocument();
  });

  it("counts pending proposals on the tab", () => {
    render(
      <AiOffice
        {...props({
          proposals: [
            proposal(),
            proposal({ id: "p2" }),
            proposal({ id: "p3", status: "APPROVED" }),
          ],
        })}
      />,
    );
    expect(screen.getByRole("tab", { name: "Proposed actions (2)" })).toBeInTheDocument();
  });

  it("resets everything when the company changes (keyed remount)", async () => {
    const view = render(<AiOffice key="company-a" {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: /Analyse my active deals/ }));
    await screen.findByRole("article", { name: "Trade Director answer" });
    await userEvent.type(screen.getByLabelText("Ask the Trade Director"), "half a thought");

    view.rerender(
      <AiOffice
        key="company-b"
        {...props({ companyName: "Northwind Metals", conversations: [], proposals: [] })}
      />,
    );
    expect(screen.getByText("Northwind Metals")).toBeInTheDocument();
    expect(
      screen.queryByRole("article", { name: "Trade Director answer" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Analyse my active deals", { selector: "span" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ask the Trade Director")).toHaveValue("");
    expect(screen.getByText("No conversations yet in this company.")).toBeInTheDocument();
  });
});

describe("evidence rendering helpers", () => {
  it("renders the status card meters without a credential or URL", () => {
    render(<AiOffice {...props()} />);
    const card = screen.getByRole("region", { name: "Provider status" });
    expect(within(card).getByText("mock-trade-director-1")).toBeInTheDocument();
    expect(within(card).getByText(/Read-only access to records/)).toBeInTheDocument();
    expect(
      within(card).getByRole("progressbar", { name: "Daily token budget used" }),
    ).toBeInTheDocument();
    expect(card.textContent ?? "").not.toMatch(/api[_ ]?key|https?:\/\//i);
  });
});
