"use client";

import { useEffect } from "react";
import { FiAlertTriangle, FiX } from "react-icons/fi";
import { Modal } from "@/components/Modal";
import { LoadingButton } from "@/components/LoadingButton";

export interface SettingChange {
  name: string;
  label: string;
  from: string;
  to: string;
  /** Retrieval changes decide what may be quoted, so they get a marker. */
  retrieval: boolean;
}

/**
 * Confirms a change to what every chat runs on, listing each knob as
 * before → after so the admin sees exactly what they are about to ship.
 */
export function ConfirmSettingsDialog({
  title,
  description,
  changes,
  confirmLabel,
  busy,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  changes: SettingChange[];
  confirmLabel: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  const touchesRetrieval = changes.some((c) => c.retrieval);

  return (
    <Modal
      onOutsideClick={busy ? undefined : onCancel}
      className="w-[calc(100%-2rem)] max-w-lg"
    >
      <div className="p-6">
        <div className="flex items-start gap-3">
          <div className="pr-6">
            <h2 className="text-lg font-semibold text-strong">{title}</h2>
            <p className="mt-1 leading-6 text-default">{description}</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="ml-auto -mr-2 -mt-2 rounded-md p-2 text-subtle hover:bg-hover hover:text-strong"
            aria-label="Close"
          >
            <FiX size={18} aria-hidden="true" />
          </button>
        </div>

        <ul className="mt-4 divide-y divide-border rounded-md border border-border">
          {changes.map((change) => (
            <li
              key={change.name}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-2"
            >
              <span className="font-medium text-strong">
                {change.label}
                {change.retrieval && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-900">
                    retrieval
                  </span>
                )}
              </span>
              <span className="font-mono text-xs">
                <span className="text-subtle line-through">{change.from}</span>
                <span className="mx-1.5 text-subtle">→</span>
                <span className="font-semibold text-strong">{change.to}</span>
              </span>
            </li>
          ))}
        </ul>

        {touchesRetrieval && (
          <div className="mt-4 flex gap-2 rounded-md border-l-4 border-l-amber-500 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
            <FiAlertTriangle
              size={16}
              className="mt-0.5 shrink-0"
              aria-hidden="true"
            />
            <span>
              Retrieval settings decide which passages an answer may quote,
              including whether a dose is given at all. Check the change against
              the eval questions before saving.
            </span>
          </div>
        )}

        <p className="mt-4 text-xs text-default">
          Applies to every user from the next message. No restart. Recorded in
          the audit trail.
        </p>

        <div className="mt-5 flex justify-end gap-3 border-t border-border pt-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-border px-4 py-2 font-medium text-emphasis hover:bg-hover"
          >
            Cancel
          </button>
          <LoadingButton loading={busy} disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </LoadingButton>
        </div>
      </div>
    </Modal>
  );
}
