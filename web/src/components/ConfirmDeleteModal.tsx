import { FiAlertTriangle, FiX } from "react-icons/fi";
import { Modal } from "./Modal";

interface ConfirmDeleteModalProps {
  title: string;
  description: string;
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel?: string;
}

export function ConfirmDeleteModal({
  title,
  description,
  onCancel,
  onConfirm,
  confirmLabel = "Delete",
}: ConfirmDeleteModalProps) {
  return (
    <Modal onOutsideClick={onCancel} className="w-[calc(100%-2rem)] max-w-md">
      <div className="p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-heal-red-100 text-error">
            <FiAlertTriangle size={20} aria-hidden="true" />
          </div>
          <div className="pr-6">
            <h2 className="text-lg font-semibold text-strong">{title}</h2>
            <p className="mt-2 leading-6 text-default">{description}</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="ml-auto -mr-2 -mt-2 rounded-md p-2 text-subtle hover:bg-hover hover:text-strong"
            aria-label="Close confirmation"
          >
            <FiX size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="mt-6 flex justify-end gap-3 border-t border-border pt-4">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-4 py-2 font-medium text-emphasis hover:bg-hover"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-error px-4 py-2 font-medium text-white hover:bg-heal-red-900"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
