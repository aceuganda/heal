"use client";

import {
  FiLogOut,
  FiMessageSquare,
  FiMoreHorizontal,
  FiPlusSquare,
  FiSearch,
  FiTool,
  FiUser,
} from "react-icons/fi";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { isAdminRole, User } from "@/lib/types";
import { logout } from "@/lib/user";
import { BasicClickable, BasicSelectable } from "@/components/BasicClickable";
import { ChatSessionDisplay } from "./SessionDisplay";
import { ChatSession } from "../interfaces";
import { groupSessionsByDateRange } from "../lib";


interface ChatSidebarProps {
  existingChats: ChatSession[];
  currentChatId: number | null;
  user: User | null;
}

export const ChatSidebar = ({
  existingChats,
  currentChatId,
  user,
}: ChatSidebarProps) => {
  const router = useRouter();

  const groupedChatSessions = groupSessionsByDateRange(existingChats);

  const [userInfoVisible, setUserInfoVisible] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const userInfoRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    logout().then((isSuccess) => {
      if (!isSuccess) {
        alert("Failed to logout");
      }
      router.push("/auth/login");
    });
  };

  // hides logout popup on any click outside
  const handleClickOutside = (event: MouseEvent) => {
    if (
      userInfoRef.current &&
      !userInfoRef.current.contains(event.target as Node)
    ) {
      setUserInfoVisible(false);
    }
  };

  useEffect(() => {
    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    const toggleSidebar = () => setIsSidebarOpen((isOpen) => !isOpen);
    window.addEventListener("toggle-chat-sidebar", toggleSidebar);

    return () => window.removeEventListener("toggle-chat-sidebar", toggleSidebar);
  }, []);

  // Mirrors open state back to the header's toggle button, which owns the
  // close control now (see Header.tsx), so its icon/label stay in sync even
  // when the sidebar closes itself (mobile overlay, New Chat).
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("chat-sidebar-state", { detail: isSidebarOpen })
    );
  }, [isSidebarOpen]);

  return (
    <div className="relative">
      {isSidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 top-16 z-30 cursor-default bg-ink-900/10 sm:hidden"
          onClick={() => setIsSidebarOpen(false)}
          aria-label="Close chat history"
        />
      )}
      <aside
        className={`
          fixed bottom-0 left-0 top-16 z-40 w-72 flex-col border-r border-border bg-background pt-3 shadow-xl transition-transform
          sm:relative sm:top-auto sm:bottom-auto sm:z-auto sm:h-screen sm:pt-[84px] sm:shadow-none
          ${isSidebarOpen ? "flex" : "hidden"}
        `}
        id="chat-sidebar"
      >
        <Link
          href="/chat"
          className="mx-3 mt-3"
          onClick={() => setIsSidebarOpen(false)}
        >
          <BasicClickable fullWidth>
            <div className="flex text-sm">
              <FiPlusSquare className="my-auto mr-2" /> New Chat
            </div>
          </BasicClickable>
        </Link>
        <div className="mt-1 pb-1 mb-1 ml-3 overflow-y-auto h-full">
          {Object.entries(groupedChatSessions).map(
            ([dateRange, chatSessions]) => {
              if (chatSessions.length > 0) {
                return (
                  <div key={dateRange}>
                    <div className="text-xs text-subtle flex pb-0.5 mb-1.5 mt-5 font-bold">
                      {dateRange}
                    </div>
                    {chatSessions.map((chat) => {
                      const isSelected = currentChatId === chat.id;
                      return (
                        <div key={chat.id} className="mr-3">
                          <ChatSessionDisplay
                            chatSession={chat}
                            isSelected={isSelected}
                          />
                        </div>
                      );
                    })}
                  </div>
                );
              }
            }
          )}
          {/* {existingChats.map((chat) => {
          const isSelected = currentChatId === chat.id;
          return (
            <div key={chat.id} className="mr-3">
              <ChatSessionDisplay chatSession={chat} isSelected={isSelected} />
            </div>
          );
        })} */}
        </div>

        <div
          className="mt-auto py-2 border-t border-border px-3"
          ref={userInfoRef}
        >
          <div className="relative text-strong">
            {userInfoVisible && (
              <div
                className={
                  (user ? "translate-y-[-110%]" : "translate-y-[-115%]") +
                  " absolute top-0 bg-background border border-border z-30 w-full rounded text-strong text-sm"
                }
              >
                {/* <Link
                  href="/search"
                  className="flex py-3 px-4 cursor-pointer hover:bg-hover"
                >
                  <FiSearch className="my-auto mr-2" />
                  Heal Search
                </Link> */}
                <Link
                  href="/chat"
                  className="flex py-3 px-4 cursor-pointer hover:bg-hover"
                >
                  <FiMessageSquare className="my-auto mr-2" />
                  Heal Chat
                </Link>
                {(!user || isAdminRole(user.role)) && (
                  <Link
                    href="/admin/sources"
                    className="flex py-3 px-4 cursor-pointer border-t border-border hover:bg-hover"
                  >
                    <FiTool className="my-auto mr-2" />
                    Admin Panel
                  </Link>
                )}
                {user && (
                  <div
                    onClick={handleLogout}
                    className="flex py-3 px-4 cursor-pointer border-t border-border rounded hover:bg-hover"
                  >
                    <FiLogOut className="my-auto mr-2" />
                    Log out
                  </div>
                )}
              </div>
            )}
            <BasicSelectable fullWidth selected={false}>
              <div
                onClick={() => setUserInfoVisible(!userInfoVisible)}
                className="flex h-8"
              >
                <div className="my-auto mr-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-heal-teal-200 bg-heal-teal-50 text-accent">
                  <FiUser size={15} aria-hidden="true" />
                </div>
                <p className="my-auto">
                  {user ? user.email : "Anonymous Possum"}
                </p>
                <FiMoreHorizontal className="my-auto ml-auto mr-2" size={20} />
              </div>
            </BasicSelectable>
          </div>
        </div>
      </aside>
    </div>
  );
};
