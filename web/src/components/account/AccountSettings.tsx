"use client";

/**
 * Your own account: profile, the two verification levels, and password.
 *
 * Shown at /account for everybody and at /admin/account inside the admin
 * panel. Its API routes skip the access policy on purpose, so a person who is
 * blocked for being unverified can still get here and do something about it.
 */

import { useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { Form, Formik } from "formik";
import { Badge, Card, Text, Title } from "@tremor/react";
import { TextFormField } from "@/components/admin/connectors/Field";
import { usePopup } from "@/components/admin/connectors/Popup";
import { LoadingButton } from "@/components/LoadingButton";
import { fetcher } from "@/lib/fetcher";
import {
  detailOf,
  MIN_PASSWORD_LENGTH,
  PasswordChange,
  passwordProblem,
  signedOutMessage,
} from "./password";
import { ProfileDraft, profileProblem, ProfileView } from "./profile";

const PROFILE_URL = "/api/manage/me/profile";

const inputClass =
  "w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-strong focus:border-heal-teal-400 focus:outline-none focus:ring-2 focus:ring-accent/20";

type SetPopup = ReturnType<typeof usePopup>["setPopup"];

function ProfileCard({
  profile,
  setPopup,
}: {
  profile: ProfileView;
  setPopup: SetPopup;
}) {
  const [draft, setDraft] = useState<ProfileDraft>({
    organisation: profile.organisation ?? "",
    date_of_birth: profile.date_of_birth ?? "",
    sex: profile.sex ?? "",
  });
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // A save re-reads the profile; follow it rather than keep a stale draft.
  useEffect(() => {
    setDraft({
      organisation: profile.organisation ?? "",
      date_of_birth: profile.date_of_birth ?? "",
      sex: profile.sex ?? "",
    });
  }, [profile.organisation, profile.date_of_birth, profile.sex]);

  const save = async () => {
    const local = profileProblem(draft, profile.sex_options);
    setProblem(local);
    if (local) return;
    setSaving(true);
    try {
      const res = await fetch(PROFILE_URL, {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...draft,
          organisation: draft.organisation.trim(),
        }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setProblem(
          detailOf(body, `Could not save your details (HTTP ${res.status})`)
        );
        return;
      }
      await mutate(PROFILE_URL, body, { revalidate: false });
      setPopup({ type: "success", message: "Your details are saved." });
    } catch (e) {
      setProblem(`Could not save your details: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <Title>Your details</Title>
      <Text className="mt-1 mb-4">
        Only you and the administrators of this deployment can see these.
      </Text>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm text-emphasis">
          Organisation
          <input
            className={inputClass}
            value={draft.organisation}
            placeholder="The hospital, clinic or programme you work for"
            onChange={(e) =>
              setDraft({ ...draft, organisation: e.target.value })
            }
            autoComplete="organization"
          />
        </label>
        <div className="flex flex-col gap-4 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1 text-sm text-emphasis">
            Date of birth
            <input
              type="date"
              className={inputClass}
              value={draft.date_of_birth}
              onChange={(e) =>
                setDraft({ ...draft, date_of_birth: e.target.value })
              }
              autoComplete="bday"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm text-emphasis">
            Sex
            <select
              className={inputClass}
              value={draft.sex}
              onChange={(e) => setDraft({ ...draft, sex: e.target.value })}
            >
              <option value="" disabled>
                Choose…
              </option>
              {Object.entries(profile.sex_options).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {problem && (
          <div role="alert" className="text-sm text-error">
            {problem}
          </div>
        )}
        <div>
          <LoadingButton loading={saving} disabled={saving} onClick={save}>
            Save details
          </LoadingButton>
        </div>
      </div>
    </Card>
  );
}

function StatusRow({
  title,
  done,
  doneText,
  pendingText,
  children,
}: {
  title: string;
  done: boolean;
  doneText: string;
  pendingText: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="font-medium text-strong">{title}</div>
        <div className="text-sm text-default">
          {done ? doneText : pendingText}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {children}
        <Badge color={done ? "emerald" : "amber"}>
          {done ? "Verified" : "Not verified"}
        </Badge>
      </div>
    </div>
  );
}

function VerificationCard({
  profile,
  setPopup,
}: {
  profile: ProfileView;
  setPopup: SetPopup;
}) {
  const [sending, setSending] = useState(false);

  const sendEmail = async () => {
    setSending(true);
    try {
      const res = await fetch("/api/manage/me/request-verification", {
        method: "POST",
        credentials: "include",
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setPopup({
          type: "error",
          message: detailOf(body, "The verification email could not be sent."),
        });
        return;
      }
      if (body?.status === "already_verified") {
        await mutate(PROFILE_URL);
        setPopup({
          type: "success",
          message: "Your email is already verified.",
        });
        return;
      }
      setPopup({
        type: "success",
        message: `Sent. Open the link in the email to ${profile.email} to finish.`,
      });
    } catch (e) {
      setPopup({ type: "error", message: `Could not send the email: ${e}` });
    } finally {
      setSending(false);
    }
  };

  return (
    <Card>
      <Title>Verification</Title>
      <Text className="mt-1">
        Two separate checks. You confirm your email address; an administrator
        confirms your account.
      </Text>

      {profile.access_blocked_reason && (
        <div
          role="status"
          className="mt-4 rounded-md border-l-4 border-l-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          {profile.access_blocked_reason}
        </div>
      )}
      {profile.chat_blocked && (
        <div
          role="status"
          className="mt-4 rounded-md border-l-4 border-l-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          An administrator has paused chat for your account.
        </div>
      )}

      <div className="mt-2 divide-y divide-border">
        <StatusRow
          title="Email"
          done={profile.email_verified}
          doneText={`${profile.email} is confirmed.`}
          pendingText={`Confirm ${profile.email} by opening the link we email you.`}
        >
          {!profile.email_verified && (
            <LoadingButton
              size="xs"
              variant="secondary"
              loading={sending}
              disabled={sending}
              onClick={sendEmail}
            >
              Send verification email
            </LoadingButton>
          )}
        </StatusRow>
        <StatusRow
          title="Administrator"
          done={profile.admin_verified}
          doneText={
            profile.admin_verified_at
              ? `Verified on ${new Date(
                  profile.admin_verified_at
                ).toLocaleDateString()}.`
              : "Verified."
          }
          pendingText="Waiting for an administrator to review your account. Nothing for you to do."
        />
      </div>
    </Card>
  );
}

const EMPTY_PASSWORD: PasswordChange = { current: "", next: "", confirm: "" };

function PasswordCard({
  email,
  setPopup,
}: {
  email: string;
  setPopup: SetPopup;
}) {
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <Card>
      <Title>Password</Title>
      <Text className="mt-1 mb-4">
        Use at least {MIN_PASSWORD_LENGTH} characters. Every other device signed
        in to this account will be signed out.
      </Text>

      <Formik
        initialValues={EMPTY_PASSWORD}
        onSubmit={async (values, { resetForm }) => {
          const local = passwordProblem(values, email);
          setProblem(local);
          if (local) return;

          try {
            const res = await fetch("/api/manage/me/password", {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                current_password: values.current,
                new_password: values.next,
              }),
            });
            const body = await res.json().catch(() => null);
            if (!res.ok) {
              setProblem(
                detailOf(
                  body,
                  `Could not change the password (HTTP ${res.status})`
                )
              );
              return;
            }
            resetForm();
            setPopup({
              type: "success",
              message: signedOutMessage(body?.signed_out_sessions ?? 0),
            });
          } catch (e) {
            setProblem(`Could not change the password: ${e}`);
          }
        }}
      >
        {({ isSubmitting }) => (
          <Form>
            <TextFormField
              name="current"
              label="Current password"
              type="password"
            />
            <TextFormField name="next" label="New password" type="password" />
            <TextFormField
              name="confirm"
              label="New password, again"
              type="password"
            />
            {problem && (
              <div role="alert" className="mb-3 text-sm text-error">
                {problem}
              </div>
            )}
            <LoadingButton
              type="submit"
              loading={isSubmitting}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Changing…" : "Change password"}
            </LoadingButton>
          </Form>
        )}
      </Formik>
    </Card>
  );
}

export function AccountSettings() {
  const { popup, setPopup } = usePopup();
  const { data: profile, error } = useSWR<ProfileView>(PROFILE_URL, fetcher);

  if (error)
    return <div className="text-error">Could not load your account.</div>;
  if (!profile) return <Text>Loading your account…</Text>;

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      {popup}
      <Text>Signed in as {profile.email}.</Text>
      <VerificationCard profile={profile} setPopup={setPopup} />
      <ProfileCard profile={profile} setPopup={setPopup} />
      <PasswordCard email={profile.email} setPopup={setPopup} />
    </div>
  );
}
