import {
  FiCheck,
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
  messageIdTranslating
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
}) => {
  const [copyClicked, setCopyClicked] = useState(false);
  return (
    <div className={"py-5 px-5 flex -mr-6 w-full"}>
      <div className="sm:mx-auto w-searchbar-xs 2xl:w-searchbar-sm 3xl:w-searchbar relative">
        <div className="sm:ml-8 ml-[0.5rem]">
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

          <div className="w-message-xs 2xl:w-message-sm 3xl:w-message-default break-words mt-1 sm:ml-8">
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
                          className="text-blue-500 hover:text-blue-700"
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
                  color="#3b82f6"
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
                <b className="text-sm text-emphasis">Sources:</b>
                <div className="flex flex-wrap gap-2">
                  {citedDocuments
                    .filter(([_, document]) => document.semantic_identifier)
                    .map(([citationKey, document], ind) => {
                      const display = (
                        <div className="max-w-350 text-ellipsis flex text-sm border border-border py-1 px-2 rounded flex">
                          <div className="mr-1 my-auto">
                            <SourceIcon
                              sourceType={document.source_type}
                              iconSize={16}
                            />
                          </div>
                          [{citationKey}] {document!.semantic_identifier}
                        </div>
                      );
                      if (document.link) {
                        return (
                          <a
                            key={document.document_id}
                            href={document.link}
                            target="_blank"
                            className="cursor-pointer hover:bg-hover"
                          >
                            {display}
                          </a>
                        );
                      } else {
                        return (
                          <div
                            key={document.document_id}
                            className="cursor-default"
                          >
                            {display}
                          </div>
                        );
                      }
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
                  className="text-blue-500 text-[10px] ml-8 "
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
    <div className="py-5 px-5 flex flex-col -mr-6 w-full">
      <div className="sm:mx-auto w-searchbar-xs 2xl:w-searchbar-sm 3xl:w-searchbar">
        <div className="sm:ml-8 ml-[0.5rem]">
          <div className="flex">
            <div className="p-1 bg-user rounded-lg h-fit">
              <div className="text-inverted">
                <FiUser size={16} className="my-auto mx-auto" />
              </div>
            </div>

            <div className="font-bold text-emphasis ml-2 my-auto">You</div>
          </div>
          <div className="mx-auto mt-1 ml-8 w-searchbar-xs 2xl:w-searchbar-sm 3xl:w-searchbar-default flex flex-wrap">
            <div className="w-message-xs 2xl:w-message-sm 3xl:w-message-default break-words">
              {typeof content === "string" ? (
                <ReactMarkdown
                  className="prose max-w-full"
                  components={{
                    a: ({ node, ...props }) => (
                      <a
                        {...props}
                        className="text-blue-500 hover:text-blue-700"
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
              className="text-blue-500 ml-16 text-[10px]"
            >
              {messageIdTranslating && messageIdTranslating === id ? "translating..." : "Translate to Luganda"}
            </button>}
        </div>
      </div>
    </div>
  );
};
