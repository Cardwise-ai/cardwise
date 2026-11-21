import type { Metadata } from "next";
import { Wordmark } from "@/components/app/wordmark";
import { safeNextPath } from "@/lib/auth/shared";
import { isMocking } from "@/lib/env";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = { title: "Sign in" };
export const instant = false;

const notices: Record<string, string> = {
  link: "That sign-in link has expired or was already used. Request a new one.",
};

export default async function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const notice = typeof params.error === "string" ? (notices[params.error] ?? null) : null;

  return (
    <div className="flex min-h-dvh flex-col px-4">
      <main className="mx-auto w-full max-w-[400px] flex-1 pt-[max(48px,12vh)] pb-12">
        <Wordmark />
        <h1 className="mt-8 text-xl font-semibold">Sign in</h1>
        <p className="mt-1 text-muted">
          Find cards for your Commander decks and keep your chats in one place.
        </p>
        <div className="mt-6 rounded-popover border border-rule bg-panel p-6">
          <SignInForm next={next} notice={notice} mocking={isMocking} />
        </div>
      </main>
      <footer className="mx-auto w-full max-w-[400px] pb-6 text-sm text-muted">
        <p>
          Card data and images come from{" "}
          <a
            href="https://scryfall.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-ink underline decoration-rule-strong underline-offset-[3px] hover:decoration-ink"
          >
            Scryfall
          </a>
          . Cardwise is unofficial Fan Content permitted under the Fan Content Policy. Not approved
          or endorsed by Wizards. Portions of the materials used are property of Wizards of the
          Coast.
        </p>
      </footer>
    </div>
  );
}
