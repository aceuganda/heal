import { useRouter } from "next/navigation";
import { ChatSession } from "../interfaces";
import { useEffect, useState } from "react";
import { deleteChatSession, renameChatSession } from "../lib";
import { DeleteChatModal } from "../modal/DeleteChatModal";
import { BasicSelectable } from "@/components/BasicClickable";
import Link from "next/link";
import { FiCheck, FiEdit, FiMessageSquare, FiTrash, FiX } from "react-icons/fi";
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
      <Link
        className="block my-1"
        key={chatSession.id}
        href={`/chat?chatId=${chatSession.id}`}
        scroll={false}
      >
        <BasicSelectable fullWidth selected={isSelected}>
          <div className="flex items-center gap-2">
            <FiMessageSquare size={16} className="shrink-0" />
            <div className="min-w-0 flex-1">
              {isRenamingChat ? (
                <input
                  value={chatName}
                  onChange={(e) => setChatName(e.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      onRename();
                      event.preventDefault();
                    }
                  }}
                  className="-my-px px-1 mr-2 w-full rounded"
                />
              ) : (
                <p className="line-clamp-1 break-all text-ellipsis text-emphasis">
                  {chatName || "Untitled chat"}
                </p>
              )}
            </div>
            {isSelected &&
              (isRenamingChat ? (
                <div className="mt-0.5 flex shrink-0">
                  <div
                    onClick={stopRowNavigation(onRename)}
                    className={`hover:bg-black/10 p-1 -m-1 rounded`}
                  >
                    <FiCheck size={16} />
                  </div>
                  <div
                    onClick={stopRowNavigation(() => {
                      setChatName(chatSession.name);
                      setIsRenamingChat(false);
                    })}
                    className={`hover:bg-black/10 p-1 -m-1 rounded ml-2`}
                  >
                    <FiX size={16} />
                  </div>
                </div>
              ) : (
                <div className="mt-0.5 flex shrink-0">
                  <div
                    onClick={stopRowNavigation(() => setIsRenamingChat(true))}
                    className={`hover:bg-black/10 p-1 -m-1 rounded`}
                  >
                    <FiEdit size={16} />
                  </div>
                  <div
                    onClick={stopRowNavigation(() =>
                      setIsDeletionModalVisible(true)
                    )}
                    className={`hover:bg-black/10 p-1 -m-1 rounded ml-2`}
                  >
                    <FiTrash size={16} />
                  </div>
                </div>
              ))}
          </div>
        </BasicSelectable>

        {/* Outside the selectable, deliberately. Inside it, the time picked up
            the hover and selected fill and read as part of the chat's name —
            two lines of equal-looking text in one grey box. Out here it is a
            caption under the row: smaller, italic, unfilled, and quiet enough
            to be skipped by someone scanning for a conversation by title.
            Indented to the title's left edge (icon + gap + the button's own
            padding). The full timestamp is on hover. */}
        {startedAt && !isRenamingChat && (
          <p
            className="mt-0.5 pl-7 text-[10px] italic leading-3 text-subtle"
            title={fullSessionStart(chatSession.time_created)}
          >
            {startedAt}
          </p>
        )}
      </Link>
    </>
  );
}
