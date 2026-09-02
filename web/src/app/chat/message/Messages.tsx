import {
  FiCheck,
  FiActivity,
  FiChevronRight,
  FiCopy,
  FiGlobe,
  FiMessageCircle,
  // FiCpu,
  FiThumbsDown,
  FiThumbsUp,
} from "react-icons/fi";
import { FeedbackType } from "../types";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { DanswerDocument } from "@/lib/search/interfaces";
import { SearchSummary, ShowHideDocsButton } from "./SearchSummary";
import { SourceIcon } from "@/components/SourceIcon";
import { AnswerProgress } from "./AnswerProgress";
import { citationKeyFromHref, linkifyCitations } from "./citationMarkers";

export const Hoverable: React.FC<{
  children: JSX.Element;
  onClick?: () => void;
}> = ({ children, onClick }) => {
  return (
    <div
      className="hover:bg-neutral-300 p-2 rounded h-fit cursor-pointer"
      onClick={onClick}
    >
      {children}
    </div>
  );
};

/** One `[1]` inside the answer, as a button that opens the cited passage. */
const InlineCitation = ({
  citationKey,
  onClick,
}: {
  citationKey: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={`Open reference ${citationKey}`}
    className="mx-0.5 align-super rounded text-[0.7em] font-semibold leading-none text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
  >
    [{citationKey}]
  </button>
);

export const AIMessage = ({
  messageId,
  content,
  language,
  luganda_message,
  query,
  citedDocuments,
  isComplete,
  hasDocs,
  handleFeedback,
  isCurrentlyShowingRetrieved,
  handleShowRetrieved,
  handleTranslation,
  handleSearchQueryEdit,
  messageIdTranslating,
  onCitationClick,
}: {
  messageId: number | null;
  content: string | JSX.Element | null | undefined;
  language?: string | null;
  luganda_message?: string | null;
  query?: string;
  citedDocuments?: [string, DanswerDocument][] | null;
  isComplete?: boolean;
  hasDocs?: boolean;
  handleFeedback?: (feedbackType: FeedbackType) => void;
  handleTranslation: (id: number | null) => void;
  isCurrentlyShowingRetrieved?: boolean;
  handleShowRetrieved?: (messageNumber: number | null) => void;
  handleSearchQueryEdit?: (query: string) => void;
  messageIdTranslating?: number | null;
  onCitationClick?: (citationKey: string, document: DanswerDocument) => void;
}) => {
  const [copyClicked, setCopyClicked] = useState(false);

  // Marker -> the passage it points at. Only markers with an entry here are
  // made clickable, so an invented `[9]` stays plain text rather than becoming
  // a link to nothing -- which is the same call the backend makes when it
  // drops a marker past the passages it supplied.
  const citationLookup = new Map(citedDocuments || []);
  const renderedContent =
    typeof content === "string"
      ? linkifyCitations(content, new Set(citationLookup.keys()))
      : content;

  return (
    <div className="flex w-full px-4 py-5 sm:px-6">
      <div className="mx-auto w-full max-w-3xl">
        <div>
          <div className="flex">
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-heal-teal-200 bg-heal-teal-50">
              <FiActivity size={16} className="text-accent" aria-hidden="true" />
            </div>

            <div className="font-bold text-emphasis ml-2 my-auto">Heal</div>

            {/* {query === undefined &&
              hasDocs &&
              handleShowRetrieved !== undefined &&
              isCurrentlyShowingRetrieved !== undefined && (
                <div className="flex w-message-xs  2xl:w-message-sm 3xl:w-message-default absolute ml-8">
                  <div className="ml-auto">
                    <ShowHideDocsButton
                      messageId={messageId}
                      isCurrentlyShowingRetrieved={isCurrentlyShowingRetrieved}
                      handleShowRetrieved={handleShowRetrieved}
                    />
                  </div>
                </div>
              )} */}
          </div>

          <div className="mt-2 max-w-2xl break-words rounded-2xl rounded-tl-md border border-border bg-background p-4 text-emphasis shadow-sm sm:ml-9">
            {query !== undefined &&
              handleShowRetrieved !== undefined &&
              isCurrentlyShowingRetrieved !== undefined && (
                <div className="my-1">
                  <SearchSummary
                    query={query}
                    hasDocs={hasDocs || false}
                    messageId={messageId}
                    isCurrentlyShowingRetrieved={isCurrentlyShowingRetrieved}
                    handleShowRetrieved={handleShowRetrieved}
                    handleSearchQueryEdit={handleSearchQueryEdit}
                  />
                </div>
              )}

            {content ? (
              <>
                {typeof renderedContent === "string" ? (
                  <ReactMarkdown
                    className="prose max-w-full"
                    components={{
                      a: ({ node, href, children, ...props }) => {
                        // A rewritten citation marker rather than a real link.
                        const citationKey = citationKeyFromHref(href);
                        if (citationKey) {
                          const cited = citationLookup.get(citationKey);
                          // Only rewritten when the source exists, so this is
                          // belt and braces: show the marker, never a dead link.
                          return cited ? (
                            <InlineCitation
                              citationKey={citationKey}
                              onClick={() => onCitationClick?.(citationKey, cited)}
                            />
                          ) : (
                            <span>[{citationKey}]</span>
                          );
                        }
                        return (
                          <a
                            {...props}
                            href={href}
                            className="text-link hover:text-accent-hover"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {children}
                          </a>
                        );
                      },
                    }}
                  >
                    {renderedContent}
                  </ReactMarkdown>
                ) : (
                  content
                )}
              </>
            ) : isComplete ? null : (
              // An assistant message with no text yet: the answer is on its
              // way but nothing has streamed, which is exactly the silence
              // AnswerProgress exists to fill.
              <AnswerProgress className="my-auto" />
            )}
            {citedDocuments && citedDocuments.length > 0 && (
              <div className="mt-2">
                <b className="text-sm text-emphasis">References</b>
                <div className="flex flex-wrap gap-2">
                  {citedDocuments
                    .filter(([_, document]) => document.semantic_identifier)
                    .map(([citationKey, document], ind) => {
                      return (
                        <button
                          // Keyed by marker, not document_id: that is
                          // `source_id:version`, so two passages cited from one
                          // guideline share it. Markers are unique per message.
                          key={citationKey}
                          type="button"
                          onClick={() => onCitationClick?.(citationKey, document)}
                          className="group flex max-w-full items-center rounded-lg border border-border bg-background px-2.5 py-1.5 text-left text-xs text-emphasis transition-colors hover:border-heal-teal-200 hover:bg-hover-light"
                        >
                          <SourceIcon sourceType={document.source_type} iconSize={15} />
                          <span className="ml-1.5 line-clamp-1">
                            [{citationKey}] {document.semantic_identifier}
                          </span>
                          <FiChevronRight className="ml-1 shrink-0 text-subtle group-hover:text-accent" size={15} />
                        </button>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
          {handleFeedback && (
            <div className="flex flex-col gap-y-3 items-start">
              {language === 'luganda' && messageId && !luganda_message &&
                <button
                  onClick={() => handleTranslation(messageId)}
                  className="ml-8 flex items-center gap-1 text-[10px] text-link"
                >
                  <FiGlobe size={12} aria-hidden="true" />
                  {messageIdTranslating && messageIdTranslating === messageId ? "translating..." : "Translate to Luganda"}
                </button>}
              <div className="flex flex-row gap-x-0.5 ml-8 mt-1">
                <Hoverable
                  onClick={() => {
                    if (typeof content === "string") {
                      navigator.clipboard.writeText(content.toString());
                      setCopyClicked(true);
                      setTimeout(() => setCopyClicked(false), 3000);
                    }
                  }}
                >
                  {copyClicked ? <FiCheck /> : <FiCopy />}
                </Hoverable>
                <Hoverable onClick={() => handleFeedback("like")}>
                  <FiThumbsUp />
                </Hoverable>
                <Hoverable>
                  <FiThumbsDown onClick={() => handleFeedback("dislike")} />
                </Hoverable>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export const HumanMessage = ({
  id,
  content,
  language,
  luganda_message,
  handleTranslation,
  messageIdTranslating
}: {
  id: number | null;
  content: string | JSX.Element | null | undefined;
  language?: string | null;
  luganda_message?: string | null;
  handleTranslation: (id: number | null) => void;
  messageIdTranslating?: number | null;
}) => {
  return (
    <div className="flex w-full flex-col px-4 py-5 sm:px-6">
      <div className="mx-auto w-full max-w-3xl">
        <div>
          <div className="flex">
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-background-strong text-emphasis">
              <FiMessageCircle size={16} aria-hidden="true" />
            </div>

            <div className="font-bold text-emphasis ml-2 my-auto">You</div>
          </div>
          <div className="mt-2 ml-9 flex flex-wrap">
            <div className="max-w-2xl break-words rounded-2xl rounded-tl-md border border-heal-teal-100 bg-heal-teal-50/70 p-4 text-emphasis">
              {typeof content === "string" ? (
                <ReactMarkdown
                  className="prose max-w-full"
                  components={{
                    a: ({ node, ...props }) => (
                      <a
                        {...props}
                        className="text-link hover:text-accent-hover"
                        target="_blank"
                        rel="noopener noreferrer"
                      />
                    ),
                  }}
                >
                  {content}
                </ReactMarkdown>
              ) : (
                content
              )}
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-y-3 items-start">
          {language === 'luganda' && id && !luganda_message &&
            <button
              onClick={() => handleTranslation(id)}
              className="ml-16 flex items-center gap-1 text-[10px] text-link"
            >
              <FiGlobe size={12} aria-hidden="true" />
              {messageIdTranslating && messageIdTranslating === id ? "translating..." : "Translate to Luganda"}
            </button>}
        </div>
      </div>
    </div>
  );
};
