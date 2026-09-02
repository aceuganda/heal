"use client";

import { useState } from "react";
import { FiCheck } from "react-icons/fi";
import { StarRating } from "./StarRating";

/**
 * Rating plus an optional comment, inline under the answer.
 *
 * The rating posts on the click. The comment box only appears if the user asks
 * for it, because the common case is someone confirming an answer was fine and
 * a modal demanding prose for that is how feedback stops being given at all.
 */
export function FeedbackControl({
  rating,
  onRate,
  onComment,
}: {
  rating?: number;
  onRate: (rating: number) => void;
  onComment: (comment: string) => void;
}) {
  const [writing, setWriting] = useState(false);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);

  const submit = () => {
    const text = comment.trim();
    if (text) {
      onComment(text);
      setSent(true);
    }
    setWriting(false);
    setComment("");
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <StarRating rating={rating} onRate={onRate} />
        {rating !== undefined && !writing && !sent && (
          <button
            type="button"
            onClick={() => setWriting(true)}
            className="text-[11px] text-link hover:underline"
          >
            Add a comment
          </button>
        )}
        {sent && (
          <span className="flex items-center gap-1 text-[11px] text-subtle">
            <FiCheck size={12} aria-hidden="true" /> Thanks
          </span>
        )}
      </div>

      {writing && (
        <div className="flex flex-col gap-1.5">
          <textarea
            autoFocus
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
              if (e.key === "Escape") {
                setWriting(false);
                setComment("");
              }
            }}
            placeholder="What would have made this better? (optional)"
            className="w-full max-w-md resize-none rounded border border-border px-2 py-1.5 text-xs outline-none placeholder-subtle focus:border-accent"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={submit}
              disabled={!comment.trim()}
              className="rounded bg-accent px-2.5 py-1 text-[11px] font-medium text-white hover:bg-accent-hover disabled:opacity-40"
            >
              Send
            </button>
            <button
              type="button"
              onClick={() => {
                setWriting(false);
                setComment("");
              }}
              className="text-[11px] text-subtle hover:text-strong"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
