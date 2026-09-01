import {
  FiCheck,
  FiChevronRight,
  FiCopy,
  // FiCpu,
  FiThumbsDown,
  FiThumbsUp,
  FiUser,
} from "react-icons/fi";
import { FeedbackType } from "../types";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { DanswerDocument } from "@/lib/search/interfaces";
import { SearchSummary, ShowHideDocsButton } from "./SearchSummary";
import { SourceIcon } from "@/components/SourceIcon";
import { ThreeDots } from "react-loader-spinner";
import Image from "next/image";

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
  return (
    <div className="flex w-full px-4 py-5 sm:px-6">
      <div className="mx-auto w-full max-w-3xl">
        <div>
          <div className="flex">
            <div className="p-1 bg-ai rounded-lg h-fit my-auto">
              <div className="text-inverted">
                <Image
                  width={16}
                  height={16}
                  alt="Heal"
                  src="/logo.png"
                  className="my-auto mx-auto"
                />
              </div>
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

          <div className="mt-2 max-w-2xl break-words sm:ml-9">
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
              </>
            ) : isComplete ? null : (
              <div className="text-sm my-auto">
                <ThreeDots
                  height="30"
                  width="50"
                  color="#0f766e"
                  ariaLabel="grid-loading"
                  radius="12.5"
                  wrapperStyle={{}}
                  wrapperClass=""
                  visible={true}
                />
              </div>
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
                          key={document.document_id}
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
                  className="text-link text-[10px] ml-8 "
                >
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
            <div className="p-1 bg-user rounded-lg h-fit">
              <div className="text-inverted">
                <FiUser size={16} className="my-auto mx-auto" />
              </div>
            </div>

            <div className="font-bold text-emphasis ml-2 my-auto">You</div>
          </div>
          <div className="mt-2 ml-9 flex flex-wrap">
            <div className="max-w-2xl break-words">
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
              className="text-link ml-16 text-[10px]"
            >
              {messageIdTranslating && messageIdTranslating === id ? "translating..." : "Translate to Luganda"}
            </button>}
        </div>
      </div>
    </div>
  );
};
