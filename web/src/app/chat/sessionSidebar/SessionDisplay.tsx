import { useRouter } from "next/navigation";
import { ChatSession } from "../interfaces";
import { useEffect, useState } from "react";
import { deleteChatSession, renameChatSession } from "../lib";
import { DeleteChatModal } from "../modal/DeleteChatModal";
import Link from "next/link";
import { FiCheck, FiEdit, FiTrash, FiX } from "react-icons/fi";
import { formatSessionStart, fullSessionStart } from "./sessionGrouping";

interface ChatSessionDisplayProps {
  chatSession: ChatSession;
  isSelected: boolean;
}

/**
 * Runs a row control's action without also following the row's link.
 *
 * Rename and delete sit inside the `<Link>` that opens the chat, so a click on
 * the bin was opening the modal and navigating to that conversation at the
 * same time — visible as the sidebar jumping under a delete confirmation.
 */
function stopRowNavigation(action: () => void) {
  return (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    action();
  };
}

/** A small icon control on a session row. Not a <button>: it sits inside
 *  the row's <Link>, and interactive content inside an anchor is invalid. */
function RowAction({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: JSX.Element;
}) {
  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={label}
      title={label}
      onClick={stopRowNavigation(onClick)}
      className="rounded-md p-1 transition-colors hover:bg-black/5 hover:text-emphasis"
    >
      {children}
    </span>
  );
}

export function ChatSessionDisplay({
  chatSession,
  isSelected,
}: ChatSessionDisplayProps) {
  const router = useRouter();
  const [isDeletionModalVisible, setIsDeletionModalVisible] = useState(false);
  const [isRenamingChat, setIsRenamingChat] = useState(false);
  const [chatName, setChatName] = useState(chatSession.name);

  // Rendered on the client only. The server and the reader's device are in
  // different time zones as often as not, and a start time formatted during
  // SSR would hydrate into a different string — React would warn, and worse,
  // whichever one a screenshot caught would be the wrong one.
  const [startedAt, setStartedAt] = useState("");
  useEffect(() => {
    setStartedAt(formatSessionStart(chatSession.time_created));
  }, [chatSession.time_created]);

  const onRename = async () => {
    const response = await renameChatSession(chatSession.id, chatName);
    if (response.ok) {
      setIsRenamingChat(false);
      router.refresh();
    } else {
      alert("Failed to rename chat session");
    }
  };

  return (
    <>
      {isDeletionModalVisible && (
        <DeleteChatModal
          onClose={() => setIsDeletionModalVisible(false)}
          onSubmit={async () => {
            const response = await deleteChatSession(chatSession.id);
            if (response.ok) {
              setIsDeletionModalVisible(false);
              // go back to the main page
              router.push("/chat");
            } else {
              alert("Failed to delete chat session");
            }
          }}
          chatSessionName={chatSession.name}
        />
      )}
      {/* Two lines, left-aligned: the title, and when it was started under
          it. This used to be a <button>, whose default centring put short
          titles in the middle of the sidebar with the date dangling outside
          the row. Now both lines share one left edge and one hover/selected
          fill, and the date is told apart from the title by size and tone
          rather than by sitting outside the box. A teal rail marks the open
          conversation. Full timestamp on hover of the caption. */}
      <Link
        key={chatSession.id}
        href={`/chat?chatId=${chatSession.id}`}
        scroll={false}
        aria-current={isSelected ? "page" : undefined}
        className={`group relative my-0.5 flex items-start gap-2 rounded-lg py-2 pl-3 pr-2 transition-colors ${
          isSelected ? "bg-hover" : "hover:bg-hover/60"
        }`}
      >
        {isSelected && (
          <span
            aria-hidden
            className="absolute bottom-2 left-0 top-2 w-[3px] rounded-full bg-accent"
          />
        )}
        <div className="min-w-0 flex-1 text-left">
          {isRenamingChat ? (
            <input
              autoFocus
              value={chatName}
              onClick={(e) => e.preventDefault()}
              onChange={(e) => setChatName(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  onRename();
                  event.preventDefault();
                }
              }}
              className="w-full rounded-md border border-border bg-background px-1.5 py-0.5 text-sm text-emphasis outline-none focus:border-accent"
            />
          ) : (
            <p
              className={`truncate text-sm leading-5 text-emphasis ${
                isSelected ? "font-semibold" : "font-medium"
              }`}
            >
              {chatName || "Untitled chat"}
            </p>
          )}
          {startedAt && (
            <p
              className="mt-0.5 truncate text-[11px] leading-4 tabular-nums text-subtle"
              title={fullSessionStart(chatSession.time_created)}
            >
              {startedAt}
            </p>
          )}
        </div>
        <div
          className={`mt-0.5 shrink-0 items-center gap-0.5 text-subtle ${
            isSelected || isRenamingChat ? "flex" : "hidden group-hover:flex"
          }`}
        >
          {isRenamingChat ? (
            <>
              <RowAction label="Save name" onClick={onRename}>
                <FiCheck size={14} />
              </RowAction>
              <RowAction
                label="Cancel rename"
                onClick={() => {
                  setChatName(chatSession.name);
                  setIsRenamingChat(false);
                }}
              >
                <FiX size={14} />
              </RowAction>
            </>
          ) : (
            <>
              <RowAction
                label="Rename chat"
                onClick={() => setIsRenamingChat(true)}
              >
                <FiEdit size={14} />
              </RowAction>
              <RowAction
                label="Delete chat"
                onClick={() => setIsDeletionModalVisible(true)}
              >
                <FiTrash size={14} />
              </RowAction>
            </>
          )}
        </div>
      </Link>
    </>
  );
}
