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
 */

import { useState } from "react";
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

function StatusPanel({ status }: { status: KnowledgeStatus | undefined }) {
  if (!status) return null;

  if (!status.enabled) {
    return (
      <Card className="mb-6">
        <Title>Retrieval is switched off</Title>
        <Text className="mt-2">
          The chat assistant is answering from general knowledge only and cannot
          cite any source. Start the stack with{" "}
          <code className="text-sm">make kb-up</code> to enable it.
        </Text>
      </Card>
    );
  }

  if (status.unavailable) {
    return (
      <Card className="mb-6 border-error">
        <Title className="text-error">Vector store unreachable</Title>
        <Text className="mt-2">{status.error}</Text>
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

function UploadPanel({ setPopup }: { setPopup: (p: any) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("1");
  const [publisher, setPublisher] = useState("");
  const [approve, setApprove] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!file || !title.trim()) {
      setPopup({ message: "A file and a title are required", type: "error" });
      return;
    }
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    body.append("title", title);
    body.append("version", version || "1");
    body.append("publisher", publisher);
    body.append("approve", String(approve));

    try {
      const res = await fetch(SOURCES_URL, { method: "POST", body });
      const payload = await res.json();
      if (!res.ok) {
        setPopup({
          message: payload.detail ?? "Upload failed",
          type: "error",
        });
      } else {
        setPopup({
          message: `Indexed ${payload.chunks_written} chunks${
            payload.approved ? "" : " — not citable until approved"
          }`,
          type: "success",
        });
        setFile(null);
        setTitle("");
        mutate(SOURCES_URL);
        mutate(STATUS_URL);
      }
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
        Text, Markdown, PDF or Word. A scanned PDF with no text layer is
        rejected rather than indexed empty.
      </Text>

      <div className="flex flex-col gap-3 max-w-2xl">
        <input
          type="file"
          accept=".txt,.md,.markdown,.text,.pdf,.docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
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
        <div>
          <Button onClick={submit} disabled={busy}>
            {busy ? "Indexing…" : "Upload and index"}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function SourcesTable({ setPopup }: { setPopup: (p: any) => void }) {
  const { data: sources, isLoading } = useSWR<SourceSummary[]>(
    SOURCES_URL,
    fetcher
  );

  const call = async (url: string, init: RequestInit, ok: string) => {
    const res = await fetch(url, init);
    if (res.ok) {
      setPopup({ message: ok, type: "success" });
      mutate(SOURCES_URL);
      mutate(STATUS_URL);
    } else {
      const body = await res.json().catch(() => ({}));
      setPopup({ message: body.detail ?? "Action failed", type: "error" });
    }
  };

  if (isLoading) return <LoadingAnimation text="Loading sources" />;
  if (!sources?.length) {
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

function SearchPanel() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!query.trim()) return;
    setBusy(true);
    const body = new FormData();
    body.append("query", query);
    const res = await fetch("/api/manage/knowledge/search", {
      method: "POST",
      body,
    });
    setResult(await res.json());
    setBusy(false);
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
        <Button onClick={run} disabled={busy}>
          {busy ? "Searching…" : "Search"}
        </Button>
      </div>

      {result && (
        <div>
          {result.unavailable && (
            <Text className="text-error">Store unreachable: {result.error}</Text>
          )}
          {!result.unavailable && result.hits.length === 0 && (
            <Text>Nothing matched at all.</Text>
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
  const { data: status } = useSWR<KnowledgeStatus>(STATUS_URL, fetcher);

  return (
    <div className="mx-auto container">
      {popup}
      <AdminPageTitle
        icon={<BookmarkIcon size={32} />}
        title="Approved sources"
      />
      <StatusPanel status={status} />
      {status?.enabled && (
        <>
          <UploadPanel setPopup={setPopup} />
          <SourcesTable setPopup={setPopup} />
          <SearchPanel />
        </>
      )}
    </div>
  );
}
