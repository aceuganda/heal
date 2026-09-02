import { DanswerDocument, Filters } from "@/lib/search/interfaces";

export enum RetrievalType {
  None = "none",
  Search = "search",
  SelectedDocs = "selectedDocs",
}

export interface RetrievalDetails {
  run_search: "always" | "never" | "auto";
  real_time: boolean;
  filters?: Filters;
  enable_auto_detect_filters?: boolean | null;
}

// Citation number -> search_doc id. The id is a UUID, carried as a string.
type CitationMap = { [key: string]: string };

export interface ChatSession {
  id: string;
  name: string;
  persona_id: number;
  time_created: string;
}

export interface Message {
  messageId: number | null;
  message: string;
  type: "user" | "assistant" | "error";
  retrievalType?: RetrievalType;
  query?: string | null;
  language?: string;
  luganda_message?: string | null;
  documents?: DanswerDocument[] | null;
  citations?: CitationMap;
}

export interface BackendChatSession {
  chat_session_id: string;
  description: string;
  persona_id: number;
  messages: BackendMessage[];
}

export interface BackendMessage {
  message_id: number;
  parent_message: number | null;
  latest_child_message: number | null;
  message: string;
  language: string;
  luganda_message: string;
  rephrased_query: string | null;
  context_docs: { top_documents: DanswerDocument[] } | null;
  message_type: "user" | "assistant" | "system";
  time_sent: string;
  citations: CitationMap;
}

/** `GET /chat/reference/{id}/gloss` -- see `heal/server/reference_api.py`.
 *  `gloss` is null when the passage could not be explained honestly; the
 *  drawer then shows the passage alone, which is what it did before. */
export interface ReferenceGloss {
  search_doc_id: string;
  gloss: string | null;
  cached: boolean;
  passage: string;
  title: string;
  /**
   * True when the model named this reference rather than the library
   * returning it. There is no passage behind it and it is never glossed — the
   * drawer shows the name and says where it came from.
   */
  external: boolean;
}

export interface DocumentsResponse {
  top_documents: DanswerDocument[];
  rephrased_query: string | null;
}

export interface StreamingError {
  error: string;
}
