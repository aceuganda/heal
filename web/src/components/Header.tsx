"use client";

import { isAdminRole, User } from "@/lib/types";
import { logout } from "@/lib/user";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { CustomDropdown, DefaultDropdownElement } from "./Dropdown";
import { FiMenu, FiMessageSquare, FiSearch, FiUser, FiX } from "react-icons/fi";
import { usePathname } from "next/navigation";

interface HeaderProps {
  user: User | null;
}

export const Header: React.FC<HeaderProps> = ({ user }) => {
  const router = useRouter();
  const pathname = usePathname();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  // Mirrors ChatSidebar's open state so this button can double as its close
  // control: icon/label reflect what a click will actually do.
  const [chatSidebarOpen, setChatSidebarOpen] = useState(true);

  useEffect(() => {
    const handleSidebarState = (event: Event) =>
      setChatSidebarOpen(Boolean((event as CustomEvent<boolean>).detail));
    window.addEventListener("chat-sidebar-state", handleSidebarState);
    return () =>
      window.removeEventListener("chat-sidebar-state", handleSidebarState);
  }, []);

  const handleLogout = async () => {
    const response = await logout();
    if (!response.ok) {
      alert("Failed to logout");
    }
    // disable auto-redirect immediately after logging out so the user
    // is not immediately re-logged in
    router.push("/auth/login?disableAutoRedirect=true");
  };

  // When dropdownOpen state changes, it attaches/removes the click listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    };

    if (dropdownOpen) {
      document.addEventListener("click", handleClickOutside);
    } else {
      document.removeEventListener("click", handleClickOutside);
    }

    // Clean up function to remove listener when component unmounts
    return () => {
      document.removeEventListener("click", handleClickOutside);
    };
  }, [dropdownOpen]);

  return (
    <header className="border-b border-border bg-background-emphasis">
      <div className="mx-4 flex h-16 sm:mx-8">
        <Link className="py-4" href="/chat">
          <div className="flex items-center gap-2 sm:gap-3">
            <div className="h-[32px] w-[30px]">
              <Image src="/logo.png" alt="Logo" width="1419" height="1520" />
            </div>
            <h1 className="flex text-xl font-bold text-strong sm:text-2xl">
              Heal
            </h1>
          </div>
        </Link>

        {pathname.startsWith("/chat") && (
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("toggle-chat-sidebar"))}
            // self-center is what was missing: the header row is `flex h-16`
            // with the default stretch alignment, and an explicit h-9 on a
            // stretched item pins it to the TOP of the 64px row. On a phone
            // the menu/close button sat a good 14px above the wordmark it is
            // meant to line up with. At sm the button goes back to filling
            // the row's height, so it stretches again there.
            className="ml-2 flex h-9 w-9 shrink-0 self-center items-center justify-center rounded-lg text-emphasis hover:bg-hover sm:ml-3 sm:h-full sm:w-auto sm:gap-2 sm:self-stretch sm:rounded-none sm:px-3"
            aria-label={chatSidebarOpen ? "Close chat history" : "Open chat history"}
            aria-pressed={chatSidebarOpen}
          >
            {chatSidebarOpen ? (
              <FiX size={18} aria-hidden="true" />
            ) : (
              <FiMenu size={18} aria-hidden="true" />
            )}
            <span className="hidden sm:inline">
              {chatSidebarOpen ? "Close" : "History"}
            </span>
          </button>
        )}

        {/* <Link
          href="/search"
          className={"ml-6 h-full flex flex-col hover:bg-hover"}
        >
          <div className="w-24 flex my-auto">
            <div className={"mx-auto flex text-strong px-2"}>
              <FiSearch className="my-auto mr-1" />
              <h1 className="flex text-sm font-bold my-auto">Search</h1>
            </div>
          </div>
        </Link> */}

        <Link href="/chat" className="hidden h-full flex-col hover:bg-hover sm:flex">
          <div className="w-24 flex my-auto">
            <div className="mx-auto flex text-strong px-2">
              <FiMessageSquare className="my-auto mr-1" />
              <h1 className="flex text-sm font-bold my-auto">Chat</h1>
            </div>
          </div>
        </Link>

        <div className="ml-auto flex h-full flex-col">
          <div className="my-auto">
            <CustomDropdown
              dropdown={
                <div
                  className={
                    "absolute right-0 mt-2 bg-background rounded border border-border " +
                    "w-48 overflow-hidden shadow-xl z-10 text-sm"
                  }
                >
                  {/* Admin panel if (1) auth is disabled or (2) user is an admin.
                      Lands on the source library: managing what the assistant
                      may cite is the job an admin opens this for. */}
                  {(!user || isAdminRole(user.role)) && (
                    <Link href="/admin/sources">
                      <DefaultDropdownElement name="Admin Panel" />
                    </Link>
                  )}
                  {user && (
                    <DefaultDropdownElement
                      name="Logout"
                      onSelect={handleLogout}
                    />
                  )}
                </div>
              }
            >
              <div className="hover:bg-hover rounded-full p-1 w-fit">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-heal-teal-200 bg-heal-teal-50 text-accent"
                  aria-label="Open account menu"
                >
                  <FiUser size={15} aria-hidden="true" />
                </div>
              </div>
            </CustomDropdown>
          </div>
        </div>
      </div>
    </header>
  );
};

/* 

*/
