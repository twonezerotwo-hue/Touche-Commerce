/** Stage 6 AI Office types, all derived from the generated OpenAPI contract. */

import type { components } from "@/lib/api/schema";

type Schemas = components["schemas"];

export type AiStatus = Schemas["AiStatusResponse"];
export type AiToolList = Schemas["AiToolListResponse"];
export type AiTool = Schemas["AiToolResponse"];
export type AiSuggestion = Schemas["SuggestionResponse"];
export type AiConversation = Schemas["ConversationResponse"];
export type AiConversationDetail = Schemas["ConversationDetailResponse"];
export type AiMessage = Schemas["MessageResponse"];
export type AiEvidence = Schemas["EvidenceResponse"];
export type AiStructuredAnswer = Schemas["StructuredAnswerResponse"];
export type AiFinding = Schemas["FindingResponse"];
export type AiRun = Schemas["RunResponse"];
export type AiToolCall = Schemas["ToolCallResponse"];
export type AiProposal = Schemas["ProposalResponse"];
export type AiSendMessageResult = Schemas["SendMessageResponse"];

export type AiBasis = AiEvidence["basis"];
export type AiRunStatus = AiRun["status"];
export type AiToolCallStatus = AiToolCall["status"];
export type AiProposalStatus = AiProposal["status"];
