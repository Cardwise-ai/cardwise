"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { sendMagicLink, type SignInState, signInWithPassword } from "./actions";

const idle: SignInState = { status: "idle" };

export function SignInForm({
  next,
  notice,
  mocking,
}: {
  next: string;
  notice: string | null;
  mocking: boolean;
}) {
  const [passwordState, passwordAction, passwordPending] = useActionState(signInWithPassword, idle);
  const [linkState, linkAction, linkPending] = useActionState(sendMagicLink, idle);
  const [last, setLast] = useState<"password" | "link" | null>(null);
  const state = last === "link" ? linkState : last === "password" ? passwordState : idle;
  const pending = passwordPending || linkPending;

  if (state.status === "sent") {
    return (
      <div role="status">
        <h2 className="text-lg font-semibold">Check your email</h2>
        <p className="mt-2 text-muted">
          We sent a sign-in link to <span className="font-semibold text-ink">{state.email}</span>.
          It expires in one hour. You can close this tab.
        </p>
        <Button className="mt-6" onClick={() => setLast(null)}>
          Use a different email
        </Button>
      </div>
    );
  }

  const error = state.status === "error" ? state.message : notice;
  return (
    <form action={passwordAction} noValidate className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />
      {error ? (
        <p
          role="alert"
          className="rounded-control border border-danger/30 bg-danger-wash px-3 py-2 text-sm"
        >
          {error}
        </p>
      ) : null}
      <Field id="email" label="Email">
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          defaultValue={state.email ?? ""}
          required
          aria-invalid={state.status === "error" ? true : undefined}
        />
      </Field>
      <Field
        id="password"
        label="Password"
        hint={mocking ? "Mock mode: any email and password will sign you in." : null}
      >
        <Input id="password" name="password" type="password" autoComplete="current-password" />
      </Field>
      <Button
        type="submit"
        variant="primary"
        disabled={pending}
        onClick={() => setLast("password")}
        className="mt-1"
      >
        {passwordPending ? "Signing in…" : "Sign in"}
      </Button>
      <div className="flex items-center gap-3 text-sm text-muted" aria-hidden>
        <span className="h-px flex-1 bg-rule" />
        or
        <span className="h-px flex-1 bg-rule" />
      </div>
      <Button
        type="submit"
        formAction={linkAction}
        disabled={pending}
        onClick={() => setLast("link")}
      >
        {linkPending ? "Sending…" : "Email me a sign-in link"}
      </Button>
    </form>
  );
}
