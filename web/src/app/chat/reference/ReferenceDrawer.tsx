import { DanswerDocument } from "@/lib/search/interfaces";
import { SourceIcon } from "@/components/SourceIcon";
import { useEffect, useState } from "react";
import { FiArrowUpRight, FiFileText, FiX } from "react-icons/fi";
import { fetchReferenceGloss } from "../lib";

export interface SelectedReference {
  citationKey: string;
  document: DanswerDocument;
}

/**
 * The plain-language gloss for the open reference, or null.
 *
 * Guarded against the reader opening a second citation before the first
 * request lands: without the cancellation flag, a slow gloss for `[1]` would
 * arrive after `[2]` was opened and be painted under `[2]`'s passage -- a
 * wrong explanation next to a dose, which is the one thing this whole path
 * exists to avoid.
 */
function useReferenceGloss(searchDocId: number | undefined) {
  const [gloss, setGloss] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setGloss(null);
    if (searchDocId === undefined || searchDocId === null) {
      // A reference with no stored row -- nothing to explain, and the panel
      // must not sit on a loading state that will never resolve.
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    fetchReferenceGloss(searchDocId).then((result) => {
      if (cancelled) {
        return;
      }
      setGloss(result?.gloss ?? null);
      setIsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [searchDocId]);

  return { gloss, isLoading };
}

function ReferenceContent({
  reference,
  onClose,
  gloss,
  isLoading,
}: {
  reference: SelectedReference;
  onClose: () => void;
  // Passed in rather than fetched here: this component is mounted twice, once
  // for the desktop panel and once for the mobile sheet, and only CSS decides
  // which is visible. Fetching inside it would generate every gloss twice.
  gloss: string | null;
  isLoading: boolean;
}) {
  const { citationKey, document } = reference;
  const excerpt = document.match_highlights?.[0] || document.blurb;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start gap-3 border-b border-border px-5 py-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-heal-teal-50 text-accent">
          <SourceIcon sourceType={document.source_type} iconSize={18} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-subtle">
            Reference [{citationKey}]
          </p>
          <h2 className="mt-0.5 line-clamp-2 text-sm font-semibold text-strong">
            {document.semantic_identifier || "Untitled source"}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close reference"
          className="rounded-md p-1.5 text-subtle hover:bg-hover hover:text-strong"
        >
          <FiX size={18} aria-hidden="true" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div className="flex items-center gap-2 text-xs text-subtle">
          <FiFileText size={14} aria-hidden="true" />
          <span>{document.source_type.replace(/_/g, " ")}</span>
        </div>

        {excerpt && (
          <div className="mt-5 rounded-xl border border-border bg-background-emphasis p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-subtle">
              Relevant excerpt
            </p>
            <p className="mt-2 text-sm leading-6 text-emphasis">{excerpt}</p>
          </div>
        )}

        {/* Below the passage, never instead of it: the guideline's own words
            are what a health worker is here to check, and the paraphrase is
            only useful once they can see what it paraphrases. Absent entirely
            when there is no gloss -- an empty "In plain language" panel would
            read as a failure rather than as the ordinary state it is. */}
        {(isLoading || gloss) && (
          <div className="mt-3 rounded-xl border border-heal-teal-200 bg-heal-teal-50/60 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-accent">
              In plain language
            </p>
            {isLoading ? (
              <div className="mt-2 space-y-2" aria-label="Loading explanation">
                <div className="h-3 w-full animate-pulse rounded bg-heal-teal-100" />
                <div className="h-3 w-2/3 animate-pulse rounded bg-heal-teal-100" />
              </div>
            ) : (
              <>
                <p className="mt-2 text-sm leading-6 text-emphasis">{gloss}</p>
                <p className="mt-2 text-xs text-subtle">
                  Generated summary of the excerpt above. Follow the excerpt,
                  not this, if they differ.
                </p>
              </>
            )}
          </div>
        )}

        {document.updated_at && (
          <p className="mt-4 text-xs text-subtle">
            Updated {new Date(document.updated_at).toLocaleDateString()}
          </p>
        )}
      </div>

      {document.link && (
        <div className="border-t border-border p-4">
          <a
            href={document.link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-accent-hover"
          >
            Open original source <FiArrowUpRight size={16} aria-hidden="true" />
          </a>
        </div>
      )}
    </div>
  );
}

export function ReferenceDrawer({
  reference,
  onClose,
}: {
  reference: SelectedReference;
  onClose: () => void;
}) {
  const { gloss, isLoading } = useReferenceGloss(reference.document.db_doc_id);

  return (
    <>
      <aside className="hidden h-screen w-80 shrink-0 border-l border-border bg-background lg:block">
        <ReferenceContent
          reference={reference}
          onClose={onClose}
          gloss={gloss}
          isLoading={isLoading}
        />
      </aside>

      <button
        type="button"
        className="fixed inset-0 z-40 bg-ink-900/20 lg:hidden"
        onClick={onClose}
        aria-label="Close reference"
      />
      <div className="fixed inset-x-0 bottom-0 z-50 max-h-[78dvh] rounded-t-2xl border border-border bg-background shadow-2xl lg:hidden">
        <div className="mx-auto mt-3 h-1.5 w-10 rounded-full bg-border-strong" />
        <div className="h-[calc(78dvh-1.125rem)]">
          <ReferenceContent
            reference={reference}
            onClose={onClose}
            gloss={gloss}
            isLoading={isLoading}
          />
        </div>
      </div>
    </>
  );
}
