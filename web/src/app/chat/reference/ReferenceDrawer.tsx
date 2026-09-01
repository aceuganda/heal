import { DanswerDocument } from "@/lib/search/interfaces";
import { SourceIcon } from "@/components/SourceIcon";
import { FiArrowUpRight, FiFileText, FiX } from "react-icons/fi";

export interface SelectedReference {
  citationKey: string;
  document: DanswerDocument;
}

function ReferenceContent({
  reference,
  onClose,
}: {
  reference: SelectedReference;
  onClose: () => void;
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
  return (
    <>
      <aside className="hidden h-screen w-80 shrink-0 border-l border-border bg-background lg:block">
        <ReferenceContent reference={reference} onClose={onClose} />
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
          <ReferenceContent reference={reference} onClose={onClose} />
        </div>
      </div>
    </>
  );
}
