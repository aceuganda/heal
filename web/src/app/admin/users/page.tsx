"use client";

/**
 * User administration.
 *
 * Accounts get created, roles get changed, and each account's verification
 * and chat access are set. The access policy at the top decides whether an
 * unverified account is blocked at all; with both switches off (the default)
 * verification is a status and nothing more.
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
import { ASSIGNABLE_ROLES, ROLE_LABELS, User, UserRole } from "@/lib/types";

const USERS_URL = "/api/manage/users";

const SEX_LABELS: Record<string, string> = {
  female: "Female",
  male: "Male",
  prefer_not_to_say: "Sex not given",
};
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

/** A small on/off switch that writes as soon as it is flipped. */
function Toggle({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 " +
        (checked ? "bg-heal-teal-700" : "bg-heal-ink-300")
      }
    >
      <span
        className={
          "inline-block h-4 w-4 rounded-full bg-white shadow transition-transform " +
          (checked ? "translate-x-[18px]" : "translate-x-0.5")
        }
      />
    </button>
  );
}

interface AccessPolicy {
  block_email_unverified: boolean;
  block_admin_unverified: boolean;
}

const POLICY_URL = "/api/manage/access-policy";

function AccessPolicyCard({ setPopup }: { setPopup: (p: any) => void }) {
  const { data, mutate: reload } = useSWR<AccessPolicy>(POLICY_URL, fetcher);
  const [busy, setBusy] = useState(false);

  const set = async (name: keyof AccessPolicy, value: boolean) => {
    setBusy(true);
    try {
      const res = await fetch(POLICY_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [name]: value }),
      });
      if (!res.ok) {
        setPopup({
          message: await errorMessage(
            res,
            "Could not change the access policy"
          ),
          type: "error",
        });
        return;
      }
      await reload(await res.json(), { revalidate: false });
      setPopup({
        message: value
          ? "Blocking is on. It applies from the next request; admins are never blocked."
          : "Blocking is off for that level.",
        type: "success",
      });
    } finally {
      setBusy(false);
    }
  };

  const rows: { name: keyof AccessPolicy; title: string; hint: string }[] = [
    {
      name: "block_email_unverified",
      title: "Block accounts without a verified email",
      hint: "They can sign in and reach Account settings to verify, but nothing else.",
    },
    {
      name: "block_admin_unverified",
      title: "Block accounts an admin has not verified",
      hint: "They can sign in and fill in their details while they wait for review.",
    },
  ];

  return (
    <Card className="mb-6">
      <Title>Access policy</Title>
      <Text className="mt-1 mb-4">
        Both off by default: verification is shown below but blocks nobody.
        Admins are never blocked by these switches.
      </Text>
      <div className="flex flex-col gap-4 max-w-2xl">
        {rows.map((row) => (
          <div
            key={row.name}
            className="flex items-start justify-between gap-4"
          >
            <div>
              <div className="text-sm font-medium text-strong">{row.title}</div>
              <div className="text-xs text-default">{row.hint}</div>
            </div>
            <Toggle
              label={row.title}
              checked={Boolean(data?.[row.name])}
              disabled={!data || busy}
              onChange={(next) => set(row.name, next)}
            />
          </div>
        ))}
      </div>
    </Card>
  );
}

function AddUserPanel({ setPopup }: { setPopup: (p: any) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("member");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!email.trim() || !password) {
      setPopup({
        message: "Email and password are both required",
        type: "error",
      });
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
        message: `${created.email} created as ${
          ROLE_LABELS[created.role as UserRole]
        }`,
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

  const changeAccess = async (
    user: User,
    change: Partial<{
      email_verified: boolean;
      admin_verified: boolean;
      chat_blocked: boolean;
    }>,
    done: string
  ) => {
    setPending(user.id);
    try {
      const res = await fetch(`${USERS_URL}/${user.id}/access`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(change),
      });
      if (!res.ok) {
        setPopup({
          message: await errorMessage(res, "Could not change the account"),
          type: "error",
        });
        return;
      }
      setPopup({ message: done, type: "success" });
      refreshUserPages();
    } catch (e) {
      setPopup({
        message: `Could not change the account: ${e}`,
        type: "error",
      });
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
            <TableHeaderCell>Account</TableHeaderCell>
            <TableHeaderCell>Email verified</TableHeaderCell>
            <TableHeaderCell>Admin verified</TableHeaderCell>
            <TableHeaderCell>Chat</TableHeaderCell>
            <TableHeaderCell>Role</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {users.map((user) => (
            <TableRow key={user.id}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-strong">{user.email}</span>
                  <Badge color={roleBadgeColor(user.role)}>
                    {ROLE_LABELS[user.role] ?? user.role}
                  </Badge>
                </div>
                <div className="mt-0.5 text-xs text-default">
                  {[
                    user.organisation,
                    user.sex ? SEX_LABELS[user.sex] ?? user.sex : null,
                    user.date_of_birth ? `born ${user.date_of_birth}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "No details yet"}
                </div>
              </TableCell>
              <TableCell>
                <Toggle
                  label={`Email verified for ${user.email}`}
                  checked={Boolean(user.is_verified)}
                  disabled={pending === user.id}
                  onChange={(next) =>
                    changeAccess(
                      user,
                      { email_verified: next },
                      next
                        ? `${user.email}'s email is marked verified`
                        : `${user.email}'s email is marked unverified`
                    )
                  }
                />
              </TableCell>
              <TableCell>
                <Toggle
                  label={`Admin verified for ${user.email}`}
                  checked={Boolean(user.admin_verified_at)}
                  disabled={pending === user.id}
                  onChange={(next) =>
                    changeAccess(
                      user,
                      { admin_verified: next },
                      next
                        ? `${user.email} is verified`
                        : `${user.email} is no longer admin-verified`
                    )
                  }
                />
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <Toggle
                    label={`Chat allowed for ${user.email}`}
                    checked={!user.chat_blocked}
                    disabled={pending === user.id}
                    onChange={(allowed) =>
                      changeAccess(
                        user,
                        { chat_blocked: !allowed },
                        allowed
                          ? `Chat is back on for ${user.email}`
                          : `Chat is paused for ${user.email}`
                      )
                    }
                  />
                  <span className="text-xs text-default">
                    {user.chat_blocked ? "Paused" : "On"}
                  </span>
                </div>
              </TableCell>
              <TableCell>
                <select
                  aria-label={`Role for ${user.email}`}
                  value={user.role === "basic" ? "member" : user.role}
                  disabled={pending === user.id}
                  onChange={(e) => changeRole(user, e.target.value as UserRole)}
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
      <AccessPolicyCard setPopup={setPopup} />
      <AddUserPanel setPopup={setPopup} />
      <UsersTable setPopup={setPopup} />
    </div>
  );
};

export default Page;
