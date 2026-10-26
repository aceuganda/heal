"use client";

import { TextFormField } from "@/components/admin/connectors/Field";
import { usePopup } from "@/components/admin/connectors/Popup";
import {
  profileProblem,
  SEX_OPTIONS,
  signupErrorMessage,
} from "@/components/account/profile";
import { basicLogin, basicSignup } from "@/lib/user";
import { Button } from "@tremor/react";
import { ErrorMessage, Field, Form, Formik } from "formik";
import { useRouter } from "next/navigation";
import * as Yup from "yup";
import { requestEmailVerification } from "../lib";
import { useState } from "react";
import { Spinner } from "@/components/Spinner";

export function EmailPasswordForm({
  isSignup = false,
  shouldVerify,
}: {
  isSignup?: boolean;
  shouldVerify?: boolean;
}) {
  const router = useRouter();
  const { popup, setPopup } = usePopup();
  const [isWorking, setIsWorking] = useState(false);

  return (
    <>
      {isWorking && <Spinner />}
      {popup}
      <Formik
        initialValues={{
          email: "",
          password: "",
          organisation: "",
          date_of_birth: "",
          sex: "",
        }}
        validationSchema={Yup.object().shape({
          email: Yup.string().email().required(),
          password: Yup.string().required(),
        })}
        // The profile rule is shared with the account page, so it runs here
        // rather than being restated in Yup.
        validate={(values) => {
          if (!isSignup) return {};
          const problem = profileProblem(values, SEX_OPTIONS);
          return problem ? { profile: problem } : {};
        }}
        onSubmit={async (values) => {
          if (isSignup) {
            // login is fast, no need to show a spinner
            setIsWorking(true);
            const { organisation, date_of_birth, sex } = values;
            const response = await basicSignup(values.email, values.password, {
              organisation,
              date_of_birth,
              sex,
            });

            if (!response.ok) {
              setIsWorking(false);
              const body = await response.json().catch(() => null);
              setPopup({
                type: "error",
                message: `Failed to sign up - ${signupErrorMessage(body)}`,
              });
              return;
            }
          }

          const loginResponse = await basicLogin(values.email, values.password);
          if (loginResponse.ok) {
            if (isSignup && shouldVerify) {
              await requestEmailVerification(values.email);
              router.push("/auth/waiting-on-verification");
            } else {
              router.push("/");
            }
          } else {
            setIsWorking(false);
            const errorDetail = (await loginResponse.json()).detail;

            let errorMsg = "Unknown error";
            if (errorDetail === "LOGIN_BAD_CREDENTIALS") {
              errorMsg = "Invalid email or password";
            }
            setPopup({
              type: "error",
              message: `Failed to login - ${errorMsg}`,
            });
          }
        }}
      >
        {({ isSubmitting, submitCount }) => (
          <Form>
            <div
              className={
                isSignup ? "grid grid-cols-1 gap-x-4 sm:grid-cols-2" : ""
              }
            >
              <TextFormField
                name="email"
                label="Email"
                type="email"
                placeholder="email@yourcompany.com"
              />

              <TextFormField
                name="password"
                label="Password"
                type="password"
                placeholder="**************"
              />

              {isSignup && (
                <>
                  <div className="sm:col-span-2">
                    <TextFormField
                      name="organisation"
                      label="Organisation"
                      placeholder="The hospital, clinic or programme you work for"
                    />
                  </div>

                  <TextFormField
                    name="date_of_birth"
                    label="Date of birth"
                    type="date"
                  />

                  <div className="mb-4">
                    <label htmlFor="sex" className="block font-medium">
                      Sex
                    </label>
                    <Field
                      as="select"
                      id="sex"
                      name="sex"
                      className="mt-1 w-full rounded border border-border bg-background-emphasis px-3 py-2"
                    >
                      <option value="" disabled>
                        Choose…
                      </option>
                      {Object.entries(SEX_OPTIONS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </Field>
                  </div>
                </>
              )}
            </div>

            {/* Shown only after a submit attempt, so an empty form is not
                greeted with an error. */}
            {isSignup && submitCount > 0 && (
              <ErrorMessage name="profile">
                {(problem) => (
                  <div role="alert" className="mb-4 text-sm text-error">
                    {problem}
                  </div>
                )}
              </ErrorMessage>
            )}

            <div className="flex">
              <Button
                type="submit"
                disabled={isSubmitting}
                className="mx-auto w-full"
              >
                {isSignup ? "Sign Up" : "Log In"}
              </Button>
            </div>
          </Form>
        )}
      </Formik>
    </>
  );
}
