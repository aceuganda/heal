"use client";

/**
 * Change your own password.
 *
 * Mainly for the bootstrap administrator: their first password came from an
 * env file, so it should be replaced at first sign-in. Changing it signs out
 * every other session of the account; this browser stays signed in.
 */

import { useState } from "react";
import useSWR from "swr";
import { Form, Formik } from "formik";
import { Card, Text, Title } from "@tremor/react";
import { AdminPageTitle } from "@/components/admin/Title";
import { TextFormField } from "@/components/admin/connectors/Field";
import { usePopup } from "@/components/admin/connectors/Popup";
import { LoadingButton } from "@/components/LoadingButton";
import { LockIcon } from "@/components/icons/icons";
import { fetcher } from "@/lib/fetcher";
import { User } from "@/lib/types";
import {
  detailOf,
  MIN_PASSWORD_LENGTH,
  PasswordChange,
  passwordProblem,
  signedOutMessage,
} from "./lib";

const EMPTY: PasswordChange = { current: "", next: "", confirm: "" };

function ChangePasswordCard({ email }: { email: string }) {
  const { popup, setPopup } = usePopup();
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <Card className="max-w-xl">
      {popup}
      <Title>Change password</Title>
      <Text className="mt-1 mb-4">
        Signed in as {email}. Use at least {MIN_PASSWORD_LENGTH} characters.
        Every other device signed in to this account will be signed out.
      </Text>

      <Formik
        initialValues={EMPTY}
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
              <div role="alert" className="text-error text-sm mb-3">
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

const Page = () => {
  const { data: user, error } = useSWR<User>("/api/manage/me", fetcher);

  return (
    <div className="mx-auto container">
      <AdminPageTitle title="Your account" icon={<LockIcon size={32} />} />
      {error && <div className="text-error">Could not load your account.</div>}
      {user && <ChangePasswordCard email={user.email} />}
    </div>
  );
};

export default Page;
