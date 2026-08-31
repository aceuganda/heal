"use client";

/**
 * Approved source library — the knowledge control centre.
 *
 * Three panels, in the order an admin actually works:
 *   1. Upload      get a document in (it lands unapproved)
 *   2. Sources     approve, supersede, remove
 *   3. Test search see real scores, including near-misses below the floor
 *
 * Panel 3 exists because MIN_RETRIEVAL_SCORE decides when Heal refuses to give
 * a dose. It cannot be chosen sensibly without seeing what a query nearly
 * matched, so this view deliberately shows hits the agent itself would drop.
 *
 * The panels always render. Retrieval is part of the stack `make up` starts,
 * so a screen that hid its own controls behind a setup instruction was telling
 * the admin to fix something that is not broken.
 */

import { useRef, useState } from "react";
import useSWR, { mutate } from "swr";
import {
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  TextInput,
  Card,
  Title,
  Text,
  Badge,
} from "@tremor/react";
import { LoadingAnimation } from "@/components/Loading";
import { AdminPageTitle } from "@/components/admin/Title";
import { usePopup } from "@/components/admin/connectors/Popup";
import { BookmarkIcon } from "@/components/icons/icons";
import { fetcher } from "@/lib/fetcher";

interface SourceSummary {
  source_id: string;
  title: string;
  version: string;
  publisher: string;
  published: string;
  approved: boolean;
  is_current: boolean;
  chunks: number;
}

interface KnowledgeStatus {
  enabled: boolean;
  unavailable?: boolean;
  error?: string;
  collection?: string;
  collection_exists?: boolean;
  points?: number;
  embedding_model?: string;
  embedding_dim?: number;
  hybrid_search?: boolean;
  min_retrieval_score?: number;
  context_top_k?: number;
  max_chunks_per_source?: number;
}

interface SearchHit {
  title: string;
  version: string;
  text: string;
  score: number;
  dense_score: number;
  sparse_score: number;
  above_floor: boolean;
}

interface SearchResponse {
  query: string;
  hits: SearchHit[];
  min_retrieval_score: number;
  best_score: number;
  below_floor: boolean;
  unavailable: boolean;
  error?: string;
}

const SOURCES_URL = "/api/manage/knowledge/sources";
const STATUS_URL = "/api/manage/knowledge/status";
const SEARCH_URL = "/api/manage/knowledge/search";

const ACCEPTED = ".txt,.md,.markdown,.text,.pdf,.docx";

/**
 * FastAPI puts the message in `detail`, which is a string for a raised
 * HTTPException and a list of objects for a validation error. Rendering the
 * latter straight into a popup produced "[object Object]", which is how a
 * legible 422 became an unexplained failure.
 */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
  const detail = body?.detail ?? body?.message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first?.msg) return `${first.msg} (${(first.loc ?? []).join(".")})`;
  }
  return `${fallback} (HTTP ${res.status})`;
}

function StatusPanel({ status }: { status: KnowledgeStatus | undefined }) {
  if (!status) return null;

  // Reached only if a deployment sets KNOWLEDGE_ENABLED=false on purpose.
  if (!status.enabled) {
    return (
      <Card className="mb-6 border-error">
        <Title className="text-error">Retrieval is switched off</Title>
        <Text className="mt-2">
          This deployment runs with <code>KNOWLEDGE_ENABLED=false</code>, so the
          assistant answers from general knowledge only and cannot cite a
          source. Nothing below will save until it is turned back on.
        </Text>
      </Card>
    );
  }

  if (status.unavailable) {
    return (
      <Card className="mb-6 border-error">
        <Title className="text-error">Vector store unreachable</Title>
        <Text className="mt-2">
          {status.error} — if the stack has just started, it is still coming up;
          this panel refreshes when you reload.
        </Text>
      </Card>
    );
  }

  return (
    <Card className="mb-6">
      <div className="flex flex-wrap gap-x-10 gap-y-3 text-sm">
        <div>
          <Text className="text-xs uppercase tracking-wide">Chunks indexed</Text>
          <div className="font-semibold">{status.points ?? 0}</div>
        </div>
        <div>
          <Text className="text-xs uppercase tracking-wide">Embedding</Text>
          <div className="font-semibold">
            {status.embedding_model} ({status.embedding_dim}d)
          </div>
        </div>
        <div>
          <Text className="text-xs uppercase tracking-wide">Hybrid search</Text>
          <div className="font-semibold">
            {status.hybrid_search ? "dense + lexical" : "dense only"}
          </div>
        </div>
        <div>
          <Text className="text-xs uppercase tracking-wide">Score floor</Text>
          <div className="font-semibold">{status.min_retrieval_score}</div>
        </div>
        <div>
          <Text className="text-xs uppercase tracking-wide">
            Chunks per answer
          </Text>
          <div className="font-semibold">
            {status.context_top_k} (max {status.max_chunks_per_source}/source)
          </div>
        </div>
      </div>
    </Card>
  );
}

/** "uganda-clinical-guidelines-2023.pdf" -> "Uganda Clinical Guidelines 2023" */
function titleFromFilename(name: string): string {
  const stem = name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
  return stem
    .split(" ")
    .filter(Boolean)
    .map((word) => (word.length > 3 ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

function UploadPanel({ setPopup }: { setPopup: (p: any) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("1");
  const [publisher, setPublisher] = useState("");
  const [approve, setApprove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const chooseFile = (chosen: File | null) => {
    setFile(chosen);
    // Filling the title from the filename is the difference between two fields
    // and four; it stays editable, and an existing title is never overwritten.
    if (chosen && !title.trim()) setTitle(titleFromFilename(chosen.name));
  };

  const clearForm = () => {
    setFile(null);
    setTitle("");
    setPublisher("");
    // The native input keeps its own filename, so clearing state alone left
    // the old name on screen next to an empty form.
    if (inputRef.current) inputRef.current.value = "";
  };

  const submit = async () => {
    if (!file) {
      setPopup({ message: "Choose a file to upload", type: "error" });
      return;
    }
    if (!title.trim()) {
      setPopup({ message: "A title is required", type: "error" });
      return;
    }
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    body.append("title", title.trim());
    body.append("version", version.trim() || "1");
    body.append("publisher", publisher.trim());
    body.append("approve", String(approve));

    try {
      const res = await fetch(SOURCES_URL, { method: "POST", body });
      if (!res.ok) {
        setPopup({
          message: await errorMessage(res, "Upload failed"),
          type: "error",
        });
        return;
      }
      const payload = await res.json();
      setPopup({
        message: `Indexed ${payload.chunks_written} chunks from ${payload.title}${
          payload.approved ? "" : " — approve it below before answers can cite it"
        }`,
        type: "success",
      });
      clearForm();
      mutate(SOURCES_URL);
      mutate(STATUS_URL);
    } catch (e) {
      setPopup({ message: `Upload failed: ${e}`, type: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-6">
      <Title>Add a source</Title>
      <Text className="mt-1 mb-4">
        Text, Markdown, PDF or Word, up to 25MB. A scanned PDF with no text
        layer is rejected rather than indexed empty.
      </Text>

      <div className="flex flex-col gap-3 max-w-2xl">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            chooseFile(e.dataTransfer.files?.[0] ?? null);
          }}
          onClick={() => inputRef.current?.click()}
          className={
            "border border-dashed rounded p-4 text-center cursor-pointer " +
            (dragging ? "border-accent bg-hover-light" : "border-border")
          }
        >
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <div className="text-sm">
              <span className="font-medium">{file.name}</span>
              <span className="text-subtle">
                {" "}
                — {(file.size / 1024).toFixed(0)} KB. Click to choose another.
              </span>
            </div>
          ) : (
            <div className="text-sm text-subtle">
              Drop a file here, or click to choose one
            </div>
          )}
        </div>

        <TextInput
          placeholder="Title, e.g. Uganda Clinical Guidelines"
          value={title}
          onValueChange={setTitle}
        />
        <div className="flex gap-3">
          <TextInput
            placeholder="Version / year"
            value={version}
            onValueChange={setVersion}
          />
          <TextInput
            placeholder="Publisher (optional)"
            value={publisher}
            onValueChange={setPublisher}
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={approve}
            onChange={(e) => setApprove(e.target.checked)}
          />
          Approve immediately — answers may cite it as soon as it is indexed
        </label>
        <div className="flex items-center gap-3">
          <Button onClick={submit} disabled={busy} loading={busy}>
            {busy ? "Indexing…" : "Upload and index"}
          </Button>
          {busy && (
            <Text className="text-xs">
              Reading, chunking and embedding the document. A large PDF takes a
              minute; leave this page open.
            </Text>
          )}
        </div>
      </div>
    </Card>
  );
}

function SourcesTable({ setPopup }: { setPopup: (p: any) => void }) {
  const { data, isLoading } = useSWR<SourceSummary[]>(SOURCES_URL, fetcher);
  // A 409 or a 500 returns an object, not an array; `.map` on it blanked the
  // whole screen with no message.
  const sources = Array.isArray(data) ? data : [];

  const call = async (url: string, init: RequestInit, ok: string) => {
    const res = await fetch(url, init);
    if (res.ok) {
      setPopup({ message: ok, type: "success" });
      mutate(SOURCES_URL);
      mutate(STATUS_URL);
    } else {
      setPopup({
        message: await errorMessage(res, "Action failed"),
        type: "error",
      });
    }
  };

  if (isLoading) return <LoadingAnimation text="Loading sources" />;
  if (!sources.length) {
    return (
      <Card>
        <Text>
          No sources yet. Until one is uploaded and approved, the assistant
          answers from general knowledge and cites nothing.
        </Text>
      </Card>
    );
  }

  return (
    <Card>
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>Title</TableHeaderCell>
            <TableHeaderCell>Version</TableHeaderCell>
            <TableHeaderCell>Chunks</TableHeaderCell>
            <TableHeaderCell>State</TableHeaderCell>
            <TableHeaderCell>Actions</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sources.map((s) => (
            <TableRow key={`${s.source_id}-${s.version}`}>
              <TableCell>
                <div className="font-medium">{s.title}</div>
                {s.publisher && (
                  <div className="text-xs text-subtle">{s.publisher}</div>
                )}
              </TableCell>
              <TableCell>{s.version}</TableCell>
              <TableCell>{s.chunks}</TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <Badge color={s.approved ? "emerald" : "amber"}>
                    {s.approved ? "Approved" : "Not approved"}
                  </Badge>
                  {!s.is_current && <Badge color="gray">Superseded</Badge>}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <Button
                    size="xs"
                    variant="secondary"
                    onClick={() =>
                      call(
                        `${SOURCES_URL}/${s.source_id}/approval`,
                        {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ approved: !s.approved }),
                        },
                        s.approved ? "Approval withdrawn" : "Source approved"
                      )
                    }
                  >
                    {s.approved ? "Withdraw" : "Approve"}
                  </Button>
                  {!s.is_current && (
                    <Button
                      size="xs"
                      variant="light"
                      onClick={() =>
                        call(
                          `${SOURCES_URL}/${s.source_id}/supersede`,
                          {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ keep_version: s.version }),
                          },
                          `v${s.version} is now the current edition`
                        )
                      }
                    >
                      Make current
                    </Button>
                  )}
                  <Button
                    size="xs"
                    variant="light"
                    color="red"
                    onClick={() => {
                      if (
                        !confirm(
                          `Delete "${s.title}" v${s.version} and all ${s.chunks} of its chunks? ` +
                            `To retire guidance that has merely been replaced, supersede it instead.`
                        )
                      )
                        return;
                      call(
                        `${SOURCES_URL}/${s.source_id}?version=${encodeURIComponent(
                          s.version
                        )}`,
                        { method: "DELETE" },
                        "Source deleted"
                      );
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

function SearchPanel({ setPopup }: { setPopup: (p: any) => void }) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!query.trim()) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append("query", query);
      const res = await fetch(SEARCH_URL, { method: "POST", body });
      if (!res.ok) {
        setPopup({
          message: await errorMessage(res, "Search failed"),
          type: "error",
        });
        setResult(null);
        return;
      }
      setResult(await res.json());
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mt-6">
      <Title>Test retrieval</Title>
      <Text className="mt-1 mb-4">
        Shows what a query matches and how strongly, including hits below the
        score floor that the assistant would discard. Try a drug code or a
        dosage — those are what dense search alone handles worst.
      </Text>

      <div className="flex gap-2 max-w-2xl mb-4">
        <TextInput
          placeholder='e.g. "TDF/3TC/DTG dose" or "500mg BD"'
          value={query}
          onValueChange={setQuery}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        <Button onClick={run} disabled={busy} loading={busy}>
          {busy ? "Searching…" : "Search"}
        </Button>
      </div>

      {result && (
        <div>
          {result.unavailable && (
            <Text className="text-error">Store unreachable: {result.error}</Text>
          )}
          {!result.unavailable && result.hits.length === 0 && (
            <Text>
              Nothing matched at all. Only approved, current sources are
              searched.
            </Text>
          )}
          {result.below_floor && (
            <Text className="text-error mb-3">
              Best score {result.best_score} is below the floor{" "}
              {result.min_retrieval_score} — the assistant would return nothing
              and refuse a dosage question.
            </Text>
          )}
          {result.hits.map((hit, i) => (
            <div
              key={i}
              className={`border-l-2 pl-3 py-2 mb-2 ${
                hit.above_floor ? "border-emerald-500" : "border-border"
              }`}
            >
              <div className="flex gap-3 text-xs">
                <span className="font-semibold">
                  {hit.score} {hit.above_floor ? "" : "(below floor)"}
                </span>
                <span className="text-subtle">
                  dense {hit.dense_score} / lexical {hit.sparse_score}
                </span>
                <span className="text-subtle">
                  {hit.title} v{hit.version}
                </span>
              </div>
              <div className="text-sm mt-1">{hit.text}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function Page() {
  const { popup, setPopup } = usePopup();
  const { data: status } = useSWR<KnowledgeStatus>(STATUS_URL, fetcher, {
    refreshInterval: 30_000,
  });

  return (
    <div className="mx-auto container">
      {popup}
      <AdminPageTitle
        icon={<BookmarkIcon size={32} />}
        title="Approved sources"
      />
      <StatusPanel status={status} />
      <UploadPanel setPopup={setPopup} />
      <SourcesTable setPopup={setPopup} />
      <SearchPanel setPopup={setPopup} />
    </div>
  );
}
