import { Header } from "@/components/Header";
import { AdminSidebar } from "@/components/admin/connectors/AdminSidebar";
import {
  KeyIcon,
  UsersIcon,
  ConnectorIcon,
  BookmarkIcon,
  NotebookIcon,
  ZoomInIcon,
} from "@/components/icons/icons";
import { isAdminRole, User } from "@/lib/types";
import {
  AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { redirect } from "next/navigation";

export async function Layout({ children }: { children: React.ReactNode }) {
  const tasks = [getAuthTypeMetadataSS(), getCurrentUserSS()];

  // catch cases where the backend is completely unreachable here
  // without try / catch, will just raise an exception and the page
  // will not render
  let results: (User | AuthTypeMetadata | null)[] = [null, null];
  try {
    results = await Promise.all(tasks);
  } catch (e) {
    console.log(`Some fetch failed for the main search page - ${e}`);
  }

  const authTypeMetadata = results[0] as AuthTypeMetadata | null;
  const user = results[1] as User | null;

  const authDisabled = authTypeMetadata?.authType === "disabled";
  const requiresVerification = authTypeMetadata?.requiresVerification;
  if (!authDisabled) {
    if (!user) {
      return redirect("/auth/login");
    }
    // Not an equality check: a super admin outranks an admin, and testing for
    // "admin" exactly would bounce them off every screen they own.
    if (!isAdminRole(user.role)) {
      return redirect("/");
    }
    if (!user.is_verified && requiresVerification) {
      return redirect("/auth/waiting-on-verification");
    }
  }

  return (
    <div className="h-screen overflow-y-hidden">
      <div className="absolute top-0 z-50 w-full">
        <Header user={user} />
      </div>
      <div className="flex h-full pt-16">
        <div className="w-80 pt-12 pb-8 h-full border-r border-border">
          <AdminSidebar
            collections={[
              // Connectors, Document Management and Custom Assistants are
              // retired: no connector fleet, no document sets, one fixed agent.
              // Knowledge replaces them: one approved library, not many sets.
              {
                name: "Knowledge",
                items: [
                  {
                    name: (
                      <div className="flex">
                        <BookmarkIcon size={18} />
                        <div className="ml-1">Approved sources</div>
                      </div>
                    ),
                    link: "/admin/sources",
                  },
                  {
                    // Sits with the library rather than under System: it is
                    // how the library's own ranking gets tuned.
                    name: (
                      <div className="flex">
                        <ZoomInIcon size={18} />
                        <div className="ml-1">Retrieval playground</div>
                      </div>
                    ),
                    link: "/admin/playground",
                  },
                ],
              },
              {
                name: "Keys",
                items: [
                  {
                    name: (
                      <div className="flex">
                        <KeyIcon size={18} />
                        <div className="ml-1">OpenAI</div>
                      </div>
                    ),
                    link: "/admin/keys/openai",
                  },
                ],
              },
              {
                name: "User Management",
                items: [
                  {
                    name: (
                      <div className="flex">
                        <UsersIcon size={18} />
                        <div className="ml-1">Users</div>
                      </div>
                    ),
                    link: "/admin/users",
                  },
                ],
              },
              {
                name: "Sessions",
                items: [
                  {
                    name: (
                      <div className="flex">
                        <ConnectorIcon size={18} />
                        <div className="ml-1">Chat sessions</div>
                      </div>
                    ),
                    link: "/admin/sessions",
                  },
                ],
              },
              {
                // The page existed but nothing linked to it, so the only way
                // to read the running versions was to type the URL.
                name: "System",
                items: [
                  {
                    name: (
                      <div className="flex">
                        <NotebookIcon size={18} />
                        <div className="ml-1">Version</div>
                      </div>
                    ),
                    link: "/admin/systeminfo",
                  },
                ],
              },
            ]}
          />
        </div>
        <div className="px-12 pt-8 pb-8 h-full overflow-y-auto w-full">
          {children}
        </div>
      </div>
    </div>
  );
}
