"use client";

/** Your own account, inside the admin panel. Same screen as /account. */

import { AdminPageTitle } from "@/components/admin/Title";
import { AccountSettings } from "@/components/account/AccountSettings";
import { LockIcon } from "@/components/icons/icons";

const Page = () => (
  <div className="mx-auto container">
    <AdminPageTitle title="Your account" icon={<LockIcon size={32} />} />
    <AccountSettings />
  </div>
);

export default Page;
