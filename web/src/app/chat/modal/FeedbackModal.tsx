"use client";

import { useState } from "react";
import { FeedbackType } from "../types";
import { FiThumbsDown, FiThumbsUp } from "react-icons/fi";
import { ModalWrapper } from "./ModalWrapper";

interface FeedbackModalProps {
  feedbackType: FeedbackType;
  onClose: () => void;
  onSubmit: (feedbackDetails: string) => void;
}

export const FeedbackModal = ({
  feedbackType,
  onClose,
  onSubmit,
}: FeedbackModalProps) => {
  const [message, setMessage] = useState("");

  return (
    <ModalWrapper onClose={onClose} modalClassName="max-w-5xl">
      <>
        <h2 className="text-2xl text-emphasis font-bold mb-1 flex">
          <div className="mr-1 my-auto">
            {feedbackType === "like" ? (
              <FiThumbsUp className="text-accent my-auto mr-2" />
            ) : (
              <FiThumbsDown className="text-red-600 my-auto mr-2" />
            )}
          </div>
          Add a comment
        </h2>
        {/* The rating is already recorded by the time this opens. Saying so
            stops the box reading as a required second step. */}
        <p className="mb-4 text-sm text-subtle">
          Optional — your {feedbackType === "like" ? "👍" : "👎"} has been
          recorded either way.
        </p>
        <textarea
          autoFocus
          className={`
              w-full
              flex-grow 
              ml-2 
              border 
              border-border-strong
              rounded 
              outline-none 
              placeholder-subtle 
              pl-4 
              pr-14 
              py-4 
              bg-background 
              overflow-hidden
              h-28
              whitespace-normal 
              resize-none
              break-all
              overscroll-contain`}
          role="textarea"
          aria-multiline
          placeholder={
            feedbackType === "like"
              ? "What did you like about this response? (optional)"
              : "What was the issue with the response? How could it be improved? (optional)"
          }
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              onSubmit(message);
              event.preventDefault();
            }
          }}
          suppressContentEditableWarning={true}
        />

        <div className="mt-3 flex items-center justify-center gap-3">
          <button
            className="rounded px-4 py-2 text-sm text-subtle hover:bg-hover hover:text-strong focus:outline-none"
            onClick={() => onSubmit("")}
          >
            Skip
          </button>
          <button
            className="bg-accent text-white py-2 px-4 rounded hover:bg-accent-hover focus:outline-none"
            onClick={() => onSubmit(message)}
          >
            {message.trim() ? "Submit comment" : "Done"}
          </button>
        </div>
      </>
    </ModalWrapper>
  );
};
