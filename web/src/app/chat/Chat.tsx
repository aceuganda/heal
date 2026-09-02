"use client";

import { useEffect, useRef, useState } from "react";
import { FiBookOpen, FiRefreshCcw, FiSend, FiStopCircle } from "react-icons/fi";
import { AIMessage, HumanMessage } from "./message/Messages";
import { AnswerPiecePacket, DanswerDocument } from "@/lib/search/interfaces";
import {
  BackendChatSession,
  BackendMessage,
  DocumentsResponse,
  Message,
  RetrievalType,
  StreamingError,
} from "./interfaces";
import { useRouter } from "next/navigation";
import {
  createChatSession,
  getCitedDocumentsFromMessage,
  getHumanAndAIMessageFromMessageNumber,
  getLastSuccessfulMessageId,
  handleAutoScroll,
  handleChatFeedback,
  nameChatSession,
  processRawChatHistory,
  sendMessage,
} from "./lib";
import { AnswerProgress } from "./message/AnswerProgress";
import { Persona } from "../admin/personas/interfaces";
import { ChatPersonaSelector } from "./ChatPersonaSelector";
import { useFilters } from "@/lib/hooks";
import { DocumentSet, Tag, ValidSources } from "@/lib/types";
import { ChatFilters } from "./modifiers/ChatFilters";
import { buildFilters } from "@/lib/search/utils";
import { SelectedDocuments } from "./modifiers/SelectedDocuments";
import { usePopup } from "@/components/admin/connectors/Popup";
import { DanswerInitializingLoader } from "@/components/DanswerInitializingLoader";
import { ChatIntro } from "./ChatIntro";
import { HEADER_PADDING } from "@/lib/constants";
import { SearchLanguageSelector } from "@/components/search/SearchLanguageSelector";
import { handleLugandaTranslation } from "./lib";
import { ReferenceDrawer, SelectedReference } from "./reference/ReferenceDrawer";

const MAX_INPUT_HEIGHT = 200;

export const Chat = ({
  existingChatSessionId,
  existingChatSessionPersonaId,
  availableSources,
  availableDocumentSets,
  availablePersonas,
  availableTags,
  defaultSelectedPersonaId,
  documentSidebarInitialWidth,
  shouldhideBeforeScroll,
}: {
  existingChatSessionId: string | null;
  existingChatSessionPersonaId: number | undefined;
  availableSources: ValidSources[];
  availableDocumentSets: DocumentSet[];
  availablePersonas: Persona[];
  availableTags: Tag[];
  defaultSelectedPersonaId?: number; // what persona to default to
  documentSidebarInitialWidth?: number;
  shouldhideBeforeScroll?: boolean;
}) => {
  const router = useRouter();
  const { popup, setPopup } = usePopup();
  const [language, setLanguage] = useState('english');

  // fetch messages for the chat session
  const [isFetchingChatMessages, setIsFetchingChatMessages] = useState(
    existingChatSessionId !== null
  );



  // this is triggered every time the user switches which chat
  // session they are using
  useEffect(() => {
    textareaRef.current?.focus();
    setChatSessionId(existingChatSessionId);
    setSelectedReference(null);

    async function initialSessionFetch() {
      if (existingChatSessionId === null) {
        setIsFetchingChatMessages(false);
        if (defaultSelectedPersonaId !== undefined) {
          setSelectedPersona(
            availablePersonas.find(
              (persona) => persona.id === defaultSelectedPersonaId
            )
          );
        } else {
          setSelectedPersona(undefined);
        }
        setMessageHistory([]);
        return;
      }

      setIsFetchingChatMessages(true);
      const response = await fetch(
        `/api/chat/get-chat-session/${existingChatSessionId}`
      );
      const chatSession = (await response.json()) as BackendChatSession;
      setSelectedPersona(
        availablePersonas.find(
          (persona) => persona.id === chatSession.persona_id
        )
      );
      const newMessageHistory = processRawChatHistory(chatSession.messages);
      setMessageHistory(newMessageHistory);

      const latestMessageId =
        newMessageHistory[newMessageHistory.length - 1]?.messageId;
      setSelectedMessageForDocDisplay(
        latestMessageId !== undefined ? latestMessageId : null
      );

      setIsFetchingChatMessages(false);
    }

    initialSessionFetch();
  }, [existingChatSessionId]);

  const backgroundRefreashChatMessages = async () => {
    const response = await fetch(
      `/api/chat/get-chat-session/${existingChatSessionId}`
    );
    const chatSession = (await response.json()) as BackendChatSession;
    setSelectedPersona(
      availablePersonas.find(
        (persona) => persona.id === chatSession.persona_id
      )
    );
    const newMessageHistory = processRawChatHistory(chatSession.messages);
    setMessageHistory(newMessageHistory);

    const latestMessageId =
      newMessageHistory[newMessageHistory.length - 1]?.messageId;
    setSelectedMessageForDocDisplay(
      latestMessageId !== undefined ? latestMessageId : null
    );
  }


  const [chatSessionId, setChatSessionId] = useState<string | null>(
    existingChatSessionId
  );
  const [message, setMessage] = useState("");
  const [messageHistory, setMessageHistory] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [messageIdTranslating, setMessageIdTranslating] = useState<number | null>(null);
  const updateLugandaPart = (messageIdToUpdate: number, luganda: string) => {
    setMessageHistory((prevMessages) =>
      prevMessages.map((message) =>
        message.messageId === messageIdToUpdate
          ? { ...message, luganda_message: luganda }
          : message
      )
    );
  };

  const handleMessageTranslation = async (messageId: number | null) => {
    if (!messageId) {
      return
    }
    setMessageIdTranslating(messageId)
    try {
      const respStream = await handleLugandaTranslation(messageId);
      const respText = await respStream.text();
      const resp = JSON.parse(respText);
      await updateLugandaPart(messageId, resp.luganda_message);
    } catch (e) {
      console.log(e)
      setMessageIdTranslating(null)
    }

  }

  // for document display
  // NOTE: -1 is a special designation that means the latest AI message
  const [selectedMessageForDocDisplay, setSelectedMessageForDocDisplay] =
    useState<number | null>(null);
  const { aiMessage } = selectedMessageForDocDisplay
    ? getHumanAndAIMessageFromMessageNumber(
      messageHistory,
      selectedMessageForDocDisplay
    )
    : { aiMessage: null };
  const [selectedDocuments, setSelectedDocuments] = useState<DanswerDocument[]>(
    []
  );
  const [selectedReference, setSelectedReference] =
    useState<SelectedReference | null>(null);
  // Set when an answer came from the cloud model because the internal one was
  // unreachable. Sticky until dismissed: it is the explanation for a change in
  // the answers, so it should outlast the turn that caused it.
  const [modelNotice, setModelNotice] = useState(false);
  const latestAssistantMessage = [...messageHistory]
    .reverse()
    .find((chatMessage) => chatMessage.type === "assistant");
  const recentReferences = latestAssistantMessage
    ? getCitedDocumentsFromMessage(latestAssistantMessage)
    : [];

  const [selectedPersona, setSelectedPersona] = useState<Persona | undefined>(
    existingChatSessionPersonaId !== undefined
      ? availablePersonas.find(
        (persona) => persona.id === existingChatSessionPersonaId
      )
      : defaultSelectedPersonaId !== undefined
        ? availablePersonas.find(
          (persona) => persona.id === defaultSelectedPersonaId
        )
        : undefined
  );
  const livePersona = selectedPersona || availablePersonas[0];

  useEffect(() => {
    if (messageHistory.length === 0) {
      setSelectedPersona(
        availablePersonas.find(
          (persona) => persona.id === defaultSelectedPersonaId
        )
      );
    }
  }, [defaultSelectedPersonaId]);

  const filterManager = useFilters();

  // state for cancelling streaming
  const [isCancelled, setIsCancelled] = useState(false);
  const isCancelledRef = useRef(isCancelled);
  useEffect(() => {
    isCancelledRef.current = isCancelled;
  }, [isCancelled]);

  // The rating each message was given, keyed by messageId, so the stars show
  // the user their click registered.
  const [givenFeedback, setGivenFeedback] = useState<Record<number, number>>({});

  // auto scroll as message comes out
  const scrollableDivRef = useRef<HTMLDivElement>(null);
  const endDivRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (isStreaming || !message) {
      handleAutoScroll(endDivRef, scrollableDivRef);
    }
  });

  /**
   * The composer overlays the message list, so the list needs a spacer exactly
   * as tall as it is or the last answer ends up underneath it.
   *
   * Measured rather than guessed. The composer's height is not one number: the
   * textarea grows with a long question, the failover notice adds a line, and
   * the recent-references row appears and disappears with the answer. The
   * fixed min-heights that used to stand in for it were right for one of those
   * states and short for the rest — and the text it hid was the end of a
   * clinical answer.
   */
  const composerRef = useRef<HTMLDivElement>(null);
  const [composerHeight, setComposerHeight] = useState(0);
  useEffect(() => {
    const node = composerRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(([entry]) =>
      setComposerHeight(entry.target.getBoundingClientRect().height)
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // scroll to bottom initially
  const [hasPerformedInitialScroll, setHasPerformedInitialScroll] = useState(
    shouldhideBeforeScroll !== true
  );
  useEffect(() => {
    endDivRef.current?.scrollIntoView();
    setHasPerformedInitialScroll(true);
  }, [isFetchingChatMessages]);

  // handle re-sizing of the text area
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "0px";
      textarea.style.height = `${Math.min(
        textarea.scrollHeight,
        MAX_INPUT_HEIGHT
      )}px`;
    }
  }, [message]);

  // used for resizing of the document sidebar
  const masterFlexboxRef = useRef<HTMLDivElement>(null);
  const [maxDocumentSidebarWidth, setMaxDocumentSidebarWidth] = useState<
    number | null
  >(null);
  const adjustDocumentSidebarWidth = () => {
    if (masterFlexboxRef.current && document.documentElement.clientWidth) {
      // numbers below are based on the actual width the center section for different
      // screen sizes. `1700` corresponds to the custom "3xl" tailwind breakpoint
      // NOTE: some buffer is needed to account for scroll bars
      if (document.documentElement.clientWidth > 1700) {
        setMaxDocumentSidebarWidth(masterFlexboxRef.current.clientWidth - 950);
      } else if (document.documentElement.clientWidth > 1420) {
        setMaxDocumentSidebarWidth(masterFlexboxRef.current.clientWidth - 760);
      } else {
        setMaxDocumentSidebarWidth(masterFlexboxRef.current.clientWidth - 660);
      }
    }
  };
  useEffect(() => {
    adjustDocumentSidebarWidth(); // Adjust the width on initial render
    window.addEventListener("resize", adjustDocumentSidebarWidth); // Add resize event listener

    return () => {
      window.removeEventListener("resize", adjustDocumentSidebarWidth); // Cleanup the event listener
    };
  }, []);

  if (!documentSidebarInitialWidth && maxDocumentSidebarWidth) {
    documentSidebarInitialWidth = Math.min(700, maxDocumentSidebarWidth);
  }

  const onSubmit = async ({
    messageIdToResend,
    queryOverride,
  }: { messageIdToResend?: number; queryOverride?: string } = {}) => {
    let currChatSessionId: string;
    let isNewSession = chatSessionId === null;
    if (isNewSession) {
      currChatSessionId = await createChatSession(livePersona?.id || 0);
    } else {
      currChatSessionId = chatSessionId as string;
    }
    setChatSessionId(currChatSessionId);

    const messageToResend = messageHistory.find(
      (message) => message.messageId === messageIdToResend
    );
    const messageToResendIndex = messageToResend
      ? messageHistory.indexOf(messageToResend)
      : null;
    if (!messageToResend && messageIdToResend !== undefined) {
      setPopup({
        message:
          "Failed to re-send message - please refresh the page and try again.",
        type: "error",
      });
      return;
    }

    const currMessage = messageToResend ? messageToResend.message : message;
    const currMessageHistory =
      messageToResendIndex !== null
        ? messageHistory.slice(0, messageToResendIndex)
        : messageHistory;
    setMessageHistory([
      ...currMessageHistory,
      {
        messageId: 0,
        message: currMessage,
        type: "user",
        language: language,
      },
    ]);
    setMessage("");

    setIsStreaming(true);
    let answer = "";
    let query: string | null = null;
    let retrievalType: RetrievalType =
      selectedDocuments.length > 0
        ? RetrievalType.SelectedDocs
        : RetrievalType.None;
    let documents: DanswerDocument[] = selectedDocuments;
    let error: string | null = null;
    let finalMessage: BackendMessage | null = null;
    try {
      const lastSuccessfulMessageId =
        getLastSuccessfulMessageId(currMessageHistory);
      for await (const packetBunch of sendMessage({
        message: currMessage,
        parentMessageId: lastSuccessfulMessageId,
        chatSessionId: currChatSessionId,
        promptId: selectedPersona?.prompts[0]?.id || 0,
        filters: buildFilters(
          filterManager.selectedSources,
          filterManager.selectedDocumentSets,
          filterManager.timeRange,
          filterManager.selectedTags
        ),
        language: language,
        selectedDocumentIds: selectedDocuments
          .filter(
            (document) =>
              document.db_doc_id !== undefined && document.db_doc_id !== null
          )
          .map((document) => document.db_doc_id as string),
        queryOverride,
      })) {
        for (const packet of packetBunch) {
          if (Object.hasOwn(packet, "answer_piece")) {
            answer += (packet as AnswerPiecePacket).answer_piece;
          } else if (Object.hasOwn(packet, "top_documents")) {
            documents = (packet as DocumentsResponse).top_documents;
            query = (packet as DocumentsResponse).rephrased_query;
            retrievalType = RetrievalType.Search;
            if (documents && documents.length > 0) {
              // point to the latest message (we don't know the messageId yet, which is why
              // we have to use -1)
              setSelectedMessageForDocDisplay(-1);
            }
          } else if (Object.hasOwn(packet, "model_notice")) {
            // The answer is fine; it just came from the cloud model because
            // the internal one did not respond. Shown once, above the input.
            setModelNotice(true);
          } else if (Object.hasOwn(packet, "error")) {
            error = (packet as StreamingError).error;
          } else if (Object.hasOwn(packet, "message_id")) {
            finalMessage = packet as BackendMessage;
          }
        }
        // console.log(finalMessage)
        setMessageHistory([
          ...currMessageHistory,
          {
            messageId: finalMessage?.parent_message || null,
            message: currMessage,
            type: "user",
            language: language,
          },
          {
            messageId: finalMessage?.message_id || null,
            message: error || finalMessage?.message || answer,
            type: error ? "error" : "assistant",
            retrievalType,
            query: finalMessage?.rephrased_query || query,
            documents: finalMessage?.context_docs?.top_documents || documents,
            citations: finalMessage?.citations || {},
            language: finalMessage?.language || language,
            luganda_message: finalMessage?.luganda_message || null,
          },
        ]);
        if (isCancelledRef.current) {
          setIsCancelled(false);
          break;
        }
      }
    } catch (e: any) {
      const errorMsg = e.message;
      setMessageHistory([
        ...currMessageHistory,
        {
          messageId: null,
          message: currMessage,
          type: "user",
          language: language,
        },
        {
          messageId: null,
          message: errorMsg,
          type: "error",
        },
      ]);
    }
    setIsStreaming(false);
    if (isNewSession) {
      if (finalMessage) {
        setSelectedMessageForDocDisplay(finalMessage.message_id);
      }
      await nameChatSession(currChatSessionId, currMessage);
      router.push(`/chat?chatId=${currChatSessionId}`, {
        scroll: false,
      });
    }
    if (
      finalMessage?.context_docs &&
      finalMessage.context_docs.top_documents.length > 0 &&
      retrievalType === RetrievalType.Search
    ) {
      setSelectedMessageForDocDisplay(finalMessage.message_id);
    }
    if (language === "luganda") {
      await backgroundRefreashChatMessages();
    }
  };

  const onFeedback = async (
    messageId: number,
    rating: number | null,
    feedbackDetails: string
  ) => {
    if (chatSessionId === null) {
      return;
    }

    const response = await handleChatFeedback(
      messageId,
      rating,
      feedbackDetails
    );

    if (response.ok) {
      if (rating !== null) {
        setGivenFeedback((prev) => ({ ...prev, [messageId]: rating }));
      }
      setPopup({
        message: "Thanks for your feedback!",
        type: "success",
      });
    } else {
      const responseJson = await response.json();
      const errorMsg = responseJson.detail || responseJson.message;
      setPopup({
        message: `Failed to submit feedback - ${errorMsg}`,
        type: "error",
      });
    }
  };

  return (
    <div className="flex w-full min-w-0 overflow-x-hidden" ref={masterFlexboxRef}>
      {popup}
      {documentSidebarInitialWidth !== undefined ? (
        <>

          <div className="relative min-w-0 flex-1">
            <div
              className={`w-full h-screen ${HEADER_PADDING} flex flex-col overflow-y-auto relative`}
              ref={scrollableDivRef}
            >
              {/* {livePersona && (
                <div className="sticky top-0 left-80 z-10 w-full bg-background/90">
                  <div className="ml-2 p-1 rounded mt-2 w-fit">
                    <ChatPersonaSelector
                      personas={availablePersonas}
                      selectedPersonaId={livePersona.id}
                      onPersonaChange={(persona) => {
                        if (persona) {
                          setSelectedPersona(persona);
                          router.push(`/chat?personaId=${persona.id}`);
                        }
                      }}
                    />
                  </div>
                </div>
              )} */}

              {messageHistory.length === 0 &&
                !isFetchingChatMessages &&
                !isStreaming && (
                  <ChatIntro
                    availableSources={availableSources}
                    availablePersonas={availablePersonas}
                    selectedPersona={selectedPersona}
                    handlePersonaSelect={(persona) => {
                      setSelectedPersona(persona);
                      router.push(`/chat?personaId=${persona.id}`);
                    }}
                    setInput={(input: string) => {
                      setMessage(input)
                    }}
                    language={language}
                  />
                )}

              <div
                className={
                  "mt-3 pt-2" +
                  (hasPerformedInitialScroll ? "" : " invisible")
                }
              >
                {messageHistory.map((message, i) => {
                  if (message.type === "user") {
                    return (
                      <div key={i}>
                        <HumanMessage content={language === "luganda" && message.luganda_message
                          ? message.luganda_message
                          : message.message}
                          id={message.messageId}
                          language={language}
                          luganda_message={message.luganda_message}
                          handleTranslation={handleMessageTranslation}
                          messageIdTranslating={messageIdTranslating}
                        />
                      </div>
                    );
                  } else if (message.type === "assistant") {
                    const isShowingRetrieved =
                      (selectedMessageForDocDisplay !== null &&
                        selectedMessageForDocDisplay === message.messageId) ||
                      (selectedMessageForDocDisplay === -1 &&
                        i === messageHistory.length - 1);
                    const previousMessage =
                      i !== 0 ? messageHistory[i - 1] : null;
                    return (
                      <div key={i}>
                        <AIMessage
                          messageId={message.messageId}
                          messageIdTranslating={messageIdTranslating}
                          handleTranslation={handleMessageTranslation}
                          language={language}
                          luganda_message={message.luganda_message}
                          content={language === "luganda" && message.luganda_message
                            ? message.luganda_message
                            : message.message}
                          query={messageHistory[i]?.query || undefined}
                          citedDocuments={getCitedDocumentsFromMessage(message)}
                          isComplete={
                            i !== messageHistory.length - 1 || !isStreaming
                          }
                          hasDocs={
                            (message.documents &&
                              message.documents.length > 0) === true
                          }
                          feedbackGiven={
                            message.messageId !== null
                              ? givenFeedback[message.messageId]
                              : undefined
                          }
                          handleFeedback={
                            i === messageHistory.length - 1 && isStreaming
                              ? undefined
                              : (rating) =>
                                onFeedback(
                                  message.messageId as number,
                                  rating,
                                  ""
                                )
                          }
                          handleComment={(comment) =>
                            onFeedback(
                              message.messageId as number,
                              null,
                              comment
                            )
                          }
                          handleSearchQueryEdit={
                            i === messageHistory.length - 1 && !isStreaming
                              ? (newQuery) => {
                                if (!previousMessage) {
                                  setPopup({
                                    type: "error",
                                    message:
                                      "Cannot edit query of first message - please refresh the page and try again.",
                                  });
                                  return;
                                }

                                if (previousMessage.messageId === null) {
                                  setPopup({
                                    type: "error",
                                    message:
                                      "Cannot edit query of a pending message - please wait a few seconds and try again.",
                                  });
                                  return;
                                }
                                onSubmit({
                                  messageIdToResend:
                                    previousMessage.messageId,
                                  queryOverride: newQuery,
                                });
                              }
                              : undefined
                          }
                          isCurrentlyShowingRetrieved={isShowingRetrieved}
                          handleShowRetrieved={(messageNumber) => {
                            if (isShowingRetrieved) {
                              setSelectedMessageForDocDisplay(null);
                            } else {
                              if (messageNumber !== null) {
                                setSelectedMessageForDocDisplay(messageNumber);
                              } else {
                                setSelectedMessageForDocDisplay(-1);
                              }
                            }
                          }}
                          onCitationClick={(citationKey, document) =>
                            setSelectedReference({ citationKey, document })
                          }
                        />
                      </div>
                    );
                  } else {
                    return (
                      <div key={i}>
                        {/* error no need for transilation */}
                        <AIMessage
                          messageId={message.messageId}
                          handleTranslation={handleMessageTranslation}
                          content={
                            <p className="text-error text-sm my-auto">
                              {message.message}
                            </p>
                          }
                        />
                      </div>
                    );
                  }
                })}

                {isStreaming &&
                  messageHistory.length &&
                  messageHistory[messageHistory.length - 1].type === "user" && (
                    <div key={messageHistory.length}>
                      <AIMessage
                        messageId={null}
                        handleTranslation={handleMessageTranslation}
                        content={<AnswerProgress className="my-auto" />}
                      />
                    </div>
                  )}

                {/* Exactly as tall as the composer that overlays this list, so
                    the last answer is never partly underneath it. The class is
                    the first-paint fallback, before the observer has measured
                    anything; after that the measured height wins. */}
                <div
                  className="w-full min-h-[140px] sm:min-h-[104px]"
                  style={
                    composerHeight
                      ? { minHeight: `${Math.ceil(composerHeight) + 16}px` }
                      : undefined
                  }
                />

                <div ref={endDivRef} />
              </div>
            </div>

            {/* The composer sits ON the page rather than on a bar laid over
                it. It used to be 95% white with a hard rule along the top —
                on the warm canvas the chat actually uses, that read as a
                paler slab pasted over the bottom of the screen. Now the ground
                is the canvas colour, fading up to nothing, so an answer
                scrolling underneath dissolves into the page instead of
                stopping at a line. The blur is what keeps text off the input
                legible through the transparent part of the fade. */}
            <div
              ref={composerRef}
              className="absolute bottom-0 max-sm:left-0 sm:z-10 w-full bg-gradient-to-b from-canvas/0 via-canvas/90 to-canvas backdrop-blur-[2px]"
            >
              {modelNotice && (
                <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-3 gap-y-1 px-4 pt-2 text-xs text-subtle sm:px-6">
                  <span>Internal model unreachable — using the cloud model.</span>
                  <button
                    type="button"
                    onClick={() => setModelNotice(false)}
                    className="font-medium text-accent hover:underline"
                  >
                    Keep using it
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setModelNotice(false);
                      router.refresh();
                    }}
                    className="font-medium text-accent hover:underline"
                  >
                    Retry the internal model
                  </button>
                </div>
              )}
              {/* The composer is the one thing permanently occupying screen
                  space, so its padding costs a line of every answer above it.
                  Trimmed to what still reads as a distinct bar. */}
              <div className="w-full pb-2 pt-1.5">
                <div className="mx-auto flex w-full max-w-3xl items-end px-3 py-1 sm:px-6">
                  <div className="relative min-w-0 flex-1">
                    {/* The field is the card, not the textarea. The border,
                        background and focus ring live out here so the language
                        pills sit INSIDE the same surface as the text — they
                        used to be absolutely positioned over the textarea,
                        paid for with a pt-12 that had to be kept in sync by
                        hand or the pills landed on the user's first line.
                        focus-within is also the only focus indicator this
                        composer has ever had; the textarea itself is
                        outline-none. */}
                    <div className="relative rounded-2xl border border-border bg-background shadow-sm transition-shadow duration-150 focus-within:border-heal-teal-200 focus-within:shadow-md focus-within:ring-2 focus-within:ring-accent/15">
                      <div className="px-2 pt-2">
                        <SearchLanguageSelector
                          language={language}
                          setLanguage={(language: string) => {
                            setLanguage(language)
                          }}
                        />
                      </div>
                    {/* {selectedDocuments.length > 0 ? (
                      <SelectedDocuments
                        selectedDocuments={selectedDocuments}
                      />
                    ) : (
                      <ChatFilters
                        {...filterManager}
                        existingSources={availableSources}
                        availableDocumentSets={availableDocumentSets}
                        availableTags={availableTags}
                      />
                    )} */}
                    <textarea
                      ref={textareaRef}
                      autoFocus
                      // Transparent and borderless: the wrapper above draws
                      // the field. min-h is now one comfortable line rather
                      // than the 80px that was reserving room for the pills.
                      className={`
                    w-full
                    shrink
                    border-0
                    bg-transparent
                    outline-none
                    placeholder-subtle
                    pl-4
                    pr-12
                    pt-1
                    pb-3
                    overflow-hidden
                    min-h-[44px]
                    ${(textareaRef?.current?.scrollHeight || 0) >
                          MAX_INPUT_HEIGHT
                          ? "overflow-y-auto"
                          : ""
                        }
                    whitespace-normal
                    break-word
                    overscroll-contain
                    resize-none
                    `}
                      style={{ scrollbarWidth: "thin" }}
                      role="textarea"
                      aria-multiline
                      placeholder={language === "luganda" ? "Nonyelezaa.." : "Ask me anything..."}
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      onKeyDown={(event) => {
                        if (
                          event.key === "Enter" &&
                          !event.shiftKey &&
                          message
                        ) {
                          onSubmit();
                          event.preventDefault();
                        }
                      }}
                      suppressContentEditableWarning={true}
                    />
                      {/* The button is the button. These classes used to sit
                          on the icon itself, which left the control with no
                          accessible name and a hit area the size of an svg. */}
                      <div className="absolute bottom-2.5 right-2.5">
                        <button
                          type="button"
                          aria-label={
                            isStreaming ? "Stop generating" : "Send message"
                          }
                          disabled={!isStreaming && !message}
                          className={
                            "flex h-9 w-9 items-center justify-center rounded-xl transition-colors " +
                            (isStreaming
                              ? "text-emphasis hover:bg-hover"
                              : message
                                ? "bg-accent text-white hover:bg-accent-hover"
                                : "cursor-not-allowed bg-background-strong text-subtle")
                          }
                          onClick={() => {
                            if (!isStreaming) {
                              if (message) {
                                onSubmit();
                              }
                            } else {
                              setIsCancelled(true);
                            }
                          }}
                        >
                          {isStreaming ? (
                            <FiStopCircle size={18} aria-hidden="true" />
                          ) : (
                            <FiSend size={18} aria-hidden="true" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {recentReferences.length > 0 && (
                  <div className="mx-auto w-full max-w-3xl px-3 pb-2 sm:px-6">
                    {/* Scrolls sideways without a visible track: this row is
                        two chips on a phone, and a scrollbar under the
                        composer reads as a second control rather than as
                        overflow. */}
                    <div className="flex items-center gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                      <span className="flex shrink-0 items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-subtle">
                        <FiBookOpen size={13} aria-hidden="true" />
                        Recent references
                      </span>
                      {recentReferences.slice(0, 2).map(([citationKey, document]) => (
                        <button
                          // See Messages.tsx: document_id is shared by every
                          // passage from one guideline, the marker is not.
                          key={citationKey}
                          type="button"
                          // Full name on hover; the chip truncates. Nullable
                          // on the wire, and `title={null}` is a type error.
                          title={document.semantic_identifier ?? undefined}
                          onClick={() => setSelectedReference({ citationKey, document })}
                          className="group flex max-w-[13rem] shrink-0 items-center gap-2 rounded-full border border-border bg-background py-1 pl-1 pr-3 text-xs text-emphasis shadow-sm transition-colors hover:border-heal-teal-200 hover:bg-hover-light"
                        >
                          {/* The marker as a badge rather than "[1] " run into
                              the title — at this size the brackets were being
                              read as part of the guideline's name. */}
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background-strong text-[10px] font-semibold text-emphasis transition-colors group-hover:bg-heal-teal-100 group-hover:text-accent">
                            {citationKey}
                          </span>
                          <span className="truncate">
                            {document.semantic_identifier}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
          {selectedReference && (
            <ReferenceDrawer
              reference={selectedReference}
              onClose={() => setSelectedReference(null)}
            />
          )}
          {/* The document-selection sidebar is retired: Phase 1 answers are
              not grounded in a document library, so there is nothing to pick
              from. It returns with the approved-source browser in Phase 2. */}
        </>
      ) : (
        <div className="mx-auto h-full flex flex-col">
          <div className="my-auto">
            <DanswerInitializingLoader />
          </div>
        </div>
      )}
    </div>
  );
};
