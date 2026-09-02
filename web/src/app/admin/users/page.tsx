"use client";

/**
 * User administration.
 *
 * Two things happen here: accounts get created, and roles get changed. Both
 * are privileged, because both are ways of handing out control of the
 * deployment.
 *
 * The role select writes immediately rather than through a save button. There
 * is one field, the change is a single request, and a save button on a
 * one-field row mostly produces rows that look changed but are not.
 */

import { useState } from "react";
import useSWR, { mutate } from "swr";
import {
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
  Button,
  Card,
  Title,
  Text,
  TextInput,
  Badge,
} from "@tremor/react";
import { LoadingAnimation } from "@/components/Loading";
import { LoadingButton } from "@/components/LoadingButton";
import { AdminPageTitle } from "@/components/admin/Title";
import { usePopup } from "@/components/admin/connectors/Popup";
import { UsersIcon } from "@/components/icons/icons";
import { fetcher } from "@/lib/fetcher";
import {
  ASSIGNABLE_ROLES,
  ROLE_LABELS,
  User,
  UserRole,
} from "@/lib/types";

const USERS_URL = "/api/manage/users";
const PAGE_SIZE = 25;

interface PaginatedUsers {
  items: User[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/**
 * Revalidate every page of the list, not one URL.
 *
 * The SWR key carries the page number and filter, so `mutate(USERS_URL)` after
 * creating a user matches nothing and the table silently keeps showing stale
 * rows. SWR 2 accepts a key matcher for exactly this.
 */
function refreshUserPages() {
  return mutate(
    (key) => typeof key === "string" && key.startsWith(USERS_URL),
    undefined,
    { revalidate: true }
  );
}

function pageUrl(page: number, email: string): string {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(PAGE_SIZE),
  });
  if (email.trim()) params.set("email", email.trim());
  return `${USERS_URL}?${params.toString()}`;
}

/**
 * FastAPI returns `detail` as a string for a raised HTTPException and as a list
 * of objects for a validation error. Rendering the latter straight into a
 * popup produces "[object Object]".
 */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    return `${fallback} (HTTP ${res.status})`;
  }
  const detail = body?.detail ?? body?.message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first?.msg) return `${first.msg} (${(first.loc ?? []).join(".")})`;
  }
  return `${fallback} (HTTP ${res.status})`;
}

function roleBadgeColor(role: UserRole): string {
  if (role === "super_admin") return "emerald";
  if (role === "admin") return "blue";
  return "gray";
}

function AddUserPanel({ setPopup }: { setPopup: (p: any) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!email.trim() || !password) {
      setPopup({ message: "Email and password are both required", type: "error" });
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(USERS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password,
          role,
        }),
      });
      if (!res.ok) {
        setPopup({
          message: await errorMessage(res, "Could not create the user"),
          type: "error",
        });
        return;
      }
      const created = await res.json();
      setPopup({
        message: `${created.email} created as ${ROLE_LABELS[created.role as UserRole]}`,
        type: "success",
      });
      setEmail("");
      setPassword("");
      setRole("member");
      refreshUserPages();
    } catch (e) {
      setPopup({ message: `Could not create the user: ${e}`, type: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-6">
      <Title>Add a user</Title>
      <Text className="mt-1 mb-4">
        The account can sign in as soon as it is created. A member sees only the
        chat; an admin also gets this panel and the source library.
      </Text>

      <div className="flex flex-col gap-3 max-w-2xl">
        <div className="flex gap-3">
          <TextInput
            placeholder="Email"
            type="email"
            value={email}
            onValueChange={setEmail}
          />
          <TextInput
            placeholder="Initial password"
            type="password"
            value={password}
            onValueChange={setPassword}
          />
        </div>
        <div className="flex gap-3 items-center">
          <label className="text-sm" htmlFor="new-user-role">
            Role
          </label>
          <select
            id="new-user-role"
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
            className="border border-border rounded p-2 text-sm bg-background"
          >
            {ASSIGNABLE_ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <LoadingButton onClick={submit} disabled={busy} loading={busy}>
            {busy ? "Creating…" : "Create user"}
          </LoadingButton>
        </div>
      </div>
    </Card>
  );
}

function UsersTable({ setPopup }: { setPopup: (p: any) => void }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const key = pageUrl(page, search);
  const { data, isLoading, error } = useSWR<PaginatedUsers>(key, fetcher);
  const [pending, setPending] = useState<string | null>(null);

  // A 403 or 500 returns an object with no `items`; reading .map off it would
  // blank the page with no explanation.
  const users = Array.isArray(data?.items) ? data!.items : [];
  const totalPages = data?.pages ?? 1;
  const total = data?.total ?? 0;

  const changeRole = async (user: User, role: UserRole) => {
    setPending(user.id);
    try {
      const res = await fetch(`${USERS_URL}/${user.id}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      if (!res.ok) {
        setPopup({
          message: await errorMessage(res, "Could not change the role"),
          type: "error",
        });
        return;
      }
      setPopup({
        message: `${user.email} is now ${ROLE_LABELS[role]}`,
        type: "success",
      });
      // A role change can move a row between filtered views, so refresh every
      // cached page rather than only the one on screen.
      refreshUserPages();
    } catch (e) {
      setPopup({ message: `Could not change the role: ${e}`, type: "error" });
    } finally {
      setPending(null);
    }
  };

  const searchBox = (
    <div className="flex gap-2 items-center mb-4 max-w-md">
      <TextInput
        placeholder="Filter by email"
        value={search}
        onValueChange={(v) => {
          setSearch(v);
          // A narrower filter can leave the current page beyond the last one,
          // which would show an empty table rather than the matches.
          setPage(1);
        }}
      />
    </div>
  );

  if (isLoading) return <LoadingAnimation text="Loading users" />;
  if (error) return <div className="text-error">Error loading users</div>;
  if (!users.length) {
    return (
      <Card>
        {searchBox}
        <Text>
          {search
            ? `No account matches "${search}".`
            : "No accounts yet. The first account created becomes the super admin, so that somebody can always manage keys and roles."}
        </Text>
      </Card>
    );
  }

  return (
    <Card>
      {searchBox}
      <Table className="overflow-visible">
        <TableHead>
          <TableRow>
            <TableHeaderCell>Email</TableHeaderCell>
            <TableHeaderCell>Status</TableHeaderCell>
            <TableHeaderCell>Role</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {users.map((user) => (
            <TableRow key={user.id}>
              <TableCell>{user.email}</TableCell>
              <TableCell>
                <div className="flex gap-2">
                  <Badge color={roleBadgeColor(user.role)}>
                    {ROLE_LABELS[user.role] ?? user.role}
                  </Badge>
                  {!user.is_verified && <Badge color="amber">Unverified</Badge>}
                </div>
              </TableCell>
              <TableCell>
                <select
                  aria-label={`Role for ${user.email}`}
                  value={user.role === "basic" ? "member" : user.role}
                  disabled={pending === user.id}
                  onChange={(e) =>
                    changeRole(user, e.target.value as UserRole)
                  }
                  className="border border-border rounded p-2 text-sm bg-background"
                >
                  {ASSIGNABLE_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="flex items-center gap-3 mt-4">
        <Text className="text-sm">
          {total} account{total === 1 ? "" : "s"} · page {data?.page ?? page} of{" "}
          {totalPages}
        </Text>
        <div className="ml-auto flex gap-2">
          <Button
            size="xs"
            variant="secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <Button
            size="xs"
            variant="secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </Button>
        </div>
      </div>
    </Card>
  );
}

const Page = () => {
  const { popup, setPopup } = usePopup();

  return (
    <div className="mx-auto container">
      {popup}
      <AdminPageTitle title="Users" icon={<UsersIcon size={32} />} />
      <AddUserPanel setPopup={setPopup} />
      <UsersTable setPopup={setPopup} />
    </div>
  );
};

export default Page;
