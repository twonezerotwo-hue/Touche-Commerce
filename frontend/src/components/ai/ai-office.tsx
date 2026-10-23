"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { History, Loader2, MessageSquarePlus, Send, Sparkles } from "lucide-react";

import { AnswerView } from "@/components/ai/answer-view";
import { ProposalCard } from "@/components/ai/proposal-card";
import { RunProgress } from "@/components/ai/run-progress";
import { ActivityList, ProviderStatusCard, ToolRegistryPanel } from "@/components/ai/side-panels";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  cancelRun,
  createConversation,
  loadActivity,
  loadConversation,
  loadProposals,
  loadRun,
  sendMessage,
} from "@/lib/ai/client";
import { describeError, isRunFinished } from "@/lib/ai/format";
import type {
  AiConversation,
  AiConversationDetail,
  AiProposal,
  AiRun,
  AiStatus,
  AiSuggestion,
  AiToolList,
} from "@/lib/ai/types";
import { cn } from "@/lib/utils";

type PanelTab = "proposals" | "activity" | "tools";

export interface AiOfficeProps {
  companyName: string;
  csrfToken: string;
  status: AiStatus;
  tools: AiToolList | null;
  suggestions: readonly AiSuggestion[];
  conversations: readonly AiConversation[];
  proposals: readonly AiProposal[];
  activity: readonly AiRun[];
  /** Milliseconds between run polls; short in tests. */
  pollIntervalMs?: number;
}

function upsert<T extends { id: string }>(list: readonly T[], item: T): T[] {
  return list.some((entry) => entry.id === item.id)
    ? list.map((entry) => (entry.id === item.id ? item : entry))
    : [item, ...list];
}

export function AiOffice({
  companyName,
  csrfToken,
  status,
  tools,
  suggestions,
  conversations: initialConversations,
  proposals: initialProposals,
  activity: initialActivity,
  pollIntervalMs = 900,
}: AiOfficeProps) {
  const [conversations, setConversations] = useState<AiConversation[]>([...initialConversations]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [thread, setThread] = useState<AiConversationDetail | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [threadError, setThreadError] = useState<string | null>(null);

  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [run, setRun] = useState<AiRun | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const [proposals, setProposals] = useState<AiProposal[]>([...initialProposals]);
  const [activity, setActivity] = useState<AiRun[]>([...initialActivity]);
  const [tab, setTab] = useState<PanelTab>("proposals");

  const bottomRef = useRef<HTMLDivElement | null>(null);
  const activeRef = useRef<string | null>(null);

  const maxChars = status.limits.max_user_message_chars;
  const running = run !== null && run.status === "RUNNING";
  const pendingCount = proposals.filter((item) => item.status === "PROPOSED").length;

  const refreshAfterRun = useCallback(async (conversationId: string): Promise<void> => {
    const [detail, props, acts] = await Promise.all([
      loadConversation(conversationId),
      loadProposals(),
      loadActivity(),
    ]);
    if (detail.ok && activeRef.current === conversationId) {
      setThread(detail.data);
      setConversations((prev) => upsert(prev, detail.data.conversation));
    }
    if (props.ok) setProposals(props.data.items);
    if (acts.ok) setActivity(acts.data.items);
  }, []);

  // Poll the in-flight run. Stops as soon as it reaches a terminal state.
  const runId = run?.id ?? null;
  const runIsRunning = run?.status === "RUNNING";
  useEffect(() => {
    if (!runId || !runIsRunning) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async (): Promise<void> => {
      const result = await loadRun(runId);
      if (cancelled) return;
      if (!result.ok) {
        setSendError(describeError(result.code, result.message));
        setRun((current) =>
          current && current.id === runId ? { ...current, status: "FAILED" } : current,
        );
        return;
      }
      setRun(result.data);
      if (isRunFinished(result.data.status)) {
        await refreshAfterRun(result.data.conversation_id);
        return;
      }
      timer = setTimeout(() => void tick(), pollIntervalMs);
    };

    timer = setTimeout(() => void tick(), pollIntervalMs);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId, runIsRunning, pollIntervalMs, refreshAfterRun]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [thread?.messages.length, run?.status]);

  async function openConversation(id: string): Promise<void> {
    if (running) return;
    activeRef.current = id;
    setActiveId(id);
    setThread(null);
    setRun(null);
    setThreadError(null);
    setSendError(null);
    setThreadLoading(true);
    const result = await loadConversation(id);
    setThreadLoading(false);
    if (activeRef.current !== id) return;
    if (!result.ok) {
      setThreadError(describeError(result.code, result.message));
      return;
    }
    setThread(result.data);
  }

  function startFresh(): void {
    if (running) return;
    activeRef.current = null;
    setActiveId(null);
    setThread(null);
    setRun(null);
    setThreadError(null);
    setSendError(null);
    setDraft("");
  }

  async function submit(text: string): Promise<void> {
    const content = text.trim();
    if (!content || sending || running || !status.enabled) return;
    setSending(true);
    setSendError(null);

    let conversationId = activeId;
    let detail = thread;
    if (!conversationId) {
      const created = await createConversation(csrfToken);
      if (!created.ok) {
        setSending(false);
        setSendError(describeError(created.code, created.message));
        return;
      }
      conversationId = created.data.id;
      detail = { conversation: created.data, messages: [], proposals: [] };
      setActiveId(conversationId);
      activeRef.current = conversationId;
      setConversations((prev) => upsert(prev, created.data));
    }

    const accepted = await sendMessage(conversationId, content, csrfToken);
    setSending(false);
    if (!accepted.ok) {
      setSendError(describeError(accepted.code, accepted.message));
      if (detail) setThread(detail);
      return;
    }
    const conversation = detail?.conversation ?? conversations.find((c) => c.id === conversationId);
    if (conversation) {
      setThread({
        conversation,
        messages: [...(detail?.messages ?? []), accepted.data.message],
        proposals: detail?.proposals ?? [],
      });
    }
    setDraft("");
    setRun(accepted.data.run);
  }

  async function cancel(): Promise<void> {
    if (!run) return;
    setCancelling(true);
    const result = await cancelRun(run.id, csrfToken);
    setCancelling(false);
    if (!result.ok) setSendError(describeError(result.code, result.message));
  }

  function onProposalChanged(updated: AiProposal): void {
    setProposals((prev) => upsert(prev, updated));
  }

  const disabled = !status.enabled;
  const orderedProposals = [
    ...proposals.filter((item) => item.status === "PROPOSED"),
    ...proposals.filter((item) => item.status !== "PROPOSED"),
  ];

  return (
    <div className="grid gap-5 xl:grid-cols-[17rem_minmax(0,1fr)_24rem]">
      {/* Left: context and history */}
      <aside className="space-y-4" aria-label="Context and history">
        <ProviderStatusCard status={status} companyName={companyName} />

        <section className="panel space-y-2 p-3" aria-label="Conversations">
          <div className="flex items-center justify-between gap-2 px-1">
            <p className="eyebrow flex items-center gap-1.5">
              <History className="size-3" aria-hidden /> History
            </p>
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={startFresh}
              disabled={running}
            >
              <MessageSquarePlus className="size-3" aria-hidden />
              New
            </Button>
          </div>
          {conversations.length === 0 ? (
            <p className="px-1 py-2 text-[11.5px] text-mist-500">
              No conversations yet in this company.
            </p>
          ) : (
            <ul className="max-h-72 space-y-0.5 overflow-auto">
              {conversations.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void openConversation(item.id)}
                    aria-current={item.id === activeId ? "true" : undefined}
                    className={cn(
                      "w-full rounded-md px-2.5 py-2 text-left transition-colors",
                      item.id === activeId
                        ? "bg-accent-400/10 text-mist-100"
                        : "text-mist-300 hover:bg-white/[0.04]",
                    )}
                  >
                    <span className="block truncate text-[12px]">{item.title}</span>
                    <span className="block font-mono text-[10px] text-mist-500">
                      {item.updated_at.slice(0, 16).replace("T", " ")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>

      {/* Centre: conversation */}
      <section className="panel flex min-h-[34rem] min-w-0 flex-col" aria-label="Conversation">
        <div className="flex-1 space-y-4 overflow-auto p-4 lg:p-5">
          {disabled ? (
            <Alert variant="warning" title="AI Office is unavailable">
              {status.notice} You can still review earlier conversations and proposals.
            </Alert>
          ) : null}

          {threadLoading ? (
            <div role="status" className="flex items-center gap-2 text-[12px] text-mist-400">
              <Loader2 className="size-3.5 animate-spin" aria-hidden /> Loading conversation…
            </div>
          ) : null}
          {threadError ? <Alert variant="danger">{threadError}</Alert> : null}

          {!thread && !threadLoading && !threadError ? (
            <EmptyState
              icon={<Sparkles className="size-5" aria-hidden />}
              title="Ask the Trade Director"
              description="It reads your deals, quotes, orders and reconciliation records, cites every source and proposes drafts or tasks for a person to approve. It cannot send, sign, pay or post anything."
              action={
                suggestions.length > 0 ? (
                  <ul
                    className="flex max-w-xl flex-wrap justify-center gap-2"
                    aria-label="Suggested questions"
                  >
                    {suggestions.map((item) => (
                      <li key={item.id}>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={disabled}
                          onClick={() => setDraft(item.prompt)}
                        >
                          {item.title}
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : undefined
              }
            />
          ) : null}

          {thread?.messages.map((message) =>
            message.role === "USER" ? (
              <div key={message.id} className="flex justify-end">
                <p className="max-w-[85%] whitespace-pre-wrap rounded-xl border border-accent-400/25 bg-accent-400/[0.08] px-3.5 py-2.5 text-[13px] leading-relaxed text-mist-100">
                  {message.content}
                </p>
              </div>
            ) : (
              <article
                key={message.id}
                aria-label="Trade Director answer"
                className="rounded-xl border border-white/8 bg-ink-850/60 p-4"
              >
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles className="size-3.5 text-accent-300" aria-hidden />
                  <span className="text-[11px] font-medium text-mist-300">Trade Director</span>
                  <Badge variant="outline">Checked against your records</Badge>
                </div>
                <AnswerView message={message} />
              </article>
            ),
          )}

          {run ? (
            <RunProgress run={run} onCancel={() => void cancel()} cancelling={cancelling} />
          ) : null}
          <div ref={bottomRef} />
        </div>

        <form
          className="space-y-2 border-t border-white/8 p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit(draft);
          }}
        >
          {sendError ? <Alert variant="danger">{sendError}</Alert> : null}
          <Label htmlFor="ai-composer">Ask the Trade Director</Label>
          <Textarea
            id="ai-composer"
            value={draft}
            rows={3}
            maxLength={maxChars}
            disabled={disabled || running}
            placeholder={
              disabled
                ? "The AI Office is unavailable."
                : "e.g. Compare the supplier quotes for my latest deal"
            }
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit(draft);
              }
            }}
          />
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10.5px] text-mist-500">
              Enter to send · Shift+Enter for a new line · {draft.length}/{maxChars}
            </p>
            <Button
              type="submit"
              size="sm"
              disabled={disabled || running || sending || draft.trim().length === 0}
            >
              {sending || running ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <Send className="size-3.5" aria-hidden />
              )}
              {running ? "Working…" : "Send"}
            </Button>
          </div>
        </form>
      </section>

      {/* Right: proposals, activity, tools */}
      <aside className="min-w-0 space-y-3" aria-label="Actions and activity">
        <div role="tablist" aria-label="Panels" className="panel flex gap-1 p-1">
          {(
            [
              ["proposals", `Proposed actions${pendingCount > 0 ? ` (${pendingCount})` : ""}`],
              ["activity", "Activity"],
              ["tools", "Tools"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`ai-tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`ai-panel-${id}`}
              onClick={() => setTab(id)}
              className={cn(
                "flex-1 rounded-md px-2 py-1.5 text-[11.5px] transition-colors",
                tab === id
                  ? "bg-white/[0.07] text-mist-100"
                  : "text-mist-400 hover:bg-white/[0.04] hover:text-mist-200",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div
          role="tabpanel"
          id={`ai-panel-${tab}`}
          aria-labelledby={`ai-tab-${tab}`}
          className="space-y-3"
        >
          {tab === "proposals" ? (
            orderedProposals.length === 0 ? (
              <EmptyState
                title="Nothing proposed yet"
                description="Drafts and tasks the assistant suggests appear here. Nothing is sent or changed until a person approves."
              />
            ) : (
              orderedProposals.map((proposal) => (
                <ProposalCard
                  key={proposal.id}
                  proposal={proposal}
                  csrfToken={csrfToken}
                  canDecide={status.can_approve}
                  onChanged={onProposalChanged}
                />
              ))
            )
          ) : null}
          {tab === "activity" ? <ActivityList runs={activity} /> : null}
          {tab === "tools" ? (
            tools ? (
              <ToolRegistryPanel tools={tools} />
            ) : (
              <Alert variant="warning">The tool list could not be loaded.</Alert>
            )
          ) : null}
        </div>
      </aside>
    </div>
  );
}
