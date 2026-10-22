"use client";

/**
 * Account settings for everybody, outside the admin panel: a member has no
 * admin surface, and this is the one settings page they get.
 */

import Link from "next/link";
import { FiArrowLeft, FiSettings } from "react-icons/fi";
import { AccountSettings } from "@/components/account/AccountSettings";

const Page = () => (
  <main className="min-h-screen bg-canvas px-4 py-6 sm:px-8">
    <div className="mx-auto max-w-2xl">
      <Link
        href="/chat"
        className="inline-flex items-center gap-1.5 text-sm text-link hover:text-accent-hover"
      >
        <FiArrowLeft aria-hidden="true" />
        Back to chat
      </Link>
      <h1 className="mt-4 mb-6 flex items-center gap-2 text-2xl font-bold text-strong">
        <FiSettings aria-hidden="true" className="text-default" />
        Account settings
      </h1>
      <AccountSettings />
    </div>
  </main>
);

export default Page;
