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
function useReferenceGloss(searchDocId: string | undefined) {
  const [gloss, setGloss] = useState<string | null>(null);
  const [isExternal, setIsExternal] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setGloss(null);
    setIsExternal(false);
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
      setIsExternal(result?.external ?? false);
      setIsLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [searchDocId]);

  return { gloss, isExternal, isLoading };
}

function ReferenceContent({
  reference,
  onClose,
  gloss,
  isExternal,
  isLoading,
}: {
  reference: SelectedReference;
  onClose: () => void;
  // Passed in rather than fetched here: this component is mounted twice, once
  // for the desktop panel and once for the mobile sheet, and only CSS decides
  // which is visible. Fetching inside it would generate every gloss twice.
  gloss: string | null;
  isExternal: boolean;
  isLoading: boolean;
}) {
  const { citationKey, document } = reference;
  // Never for an external reference: there is no passage behind it, and a
  // stored blurb that looked like one would be text nobody retrieved.
  const excerpt = isExternal
    ? null
    : document.match_highlights?.[0] || document.blurb;

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
          <span>
            {isExternal
              ? "Suggested reference"
              : document.source_type.replace(/_/g, " ")}
          </span>
        </div>

        {/* The one thing a reader must not get wrong about this panel: whether
            they are looking at words from an approved document or at the name
            of somewhere to go and check. Said plainly, at the top, in place of
            the excerpt rather than under it. */}
        {isExternal && (
          <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-amber-800">
              Not from the approved library
            </p>
            <p className="mt-2 text-xs leading-5 text-amber-900">
              The assistant named this from general knowledge. Nothing was
              retrieved and no wording from it was checked, so there is no
              excerpt to show. Look it up before acting on the answer.
            </p>
          </div>
        )}

        {excerpt && (
          <div className="mt-5 rounded-xl border border-border bg-background-emphasis p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-subtle">
              Relevant excerpt
            </p>
            <p className="mt-2 text-xs leading-5 text-emphasis">{excerpt}</p>
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
  const { gloss, isExternal, isLoading } = useReferenceGloss(
    reference.document.db_doc_id
  );

  return (
    <>
      {/* ChatLayout's header is `absolute top-0`, so it overlays this panel
          rather than pushing it down. Without the same pt-[84px] the sidebar
          uses, the close button renders underneath it and can't be clicked. */}
      <aside className="hidden h-screen w-80 shrink-0 border-l border-border bg-background lg:block lg:pt-[84px]">
        <ReferenceContent
          reference={reference}
          onClose={onClose}
          gloss={gloss}
          isExternal={isExternal}
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
            isExternal={isExternal}
            isLoading={isLoading}
          />
        </div>
      </div>
    </>
  );
}
