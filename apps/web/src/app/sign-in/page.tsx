import type { Metadata } from "next";
import { Wordmark } from "@/components/app/wordmark";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { safeNextPath } from "@/lib/auth/shared";
import { isMocking } from "@/lib/env";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = { title: "Sign in" };
export const instant = false;

const notices: Record<string, string> = {
  link: "That sign-in link has expired or was already used. Request a new one.",
  google: "Google sign-in couldn't be completed. Try again.",
  session: "Your session has ended. Sign in again to continue.",
};

export default async function SignInPage({ searchParams }: PageProps<"/sign-in">) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const notice = typeof params.error === "string" ? (notices[params.error] ?? null) : null;

  return (
    <div className="flex min-h-dvh flex-col lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(400px,0.95fr)]">
      <section
        aria-labelledby="welcome-title"
        className="dark-field flex min-h-[310px] flex-col bg-rail px-6 py-7 text-white sm:px-10 sm:py-9 lg:min-h-dvh lg:px-[clamp(48px,8vw,120px)]"
      >
        <Wordmark inverse />
        <div className="my-auto max-w-[520px] py-10 lg:py-0">
          <h1
            id="welcome-title"
            className="max-w-[12ch] text-balance text-[clamp(2.75rem,6.5vw,5.5rem)] leading-[0.94] font-bold tracking-display"
          >
            Find the card that makes the deck click.
          </h1>
          <p className="mt-5 max-w-[48ch] text-white/75">
            Ask about your commander, your strategy, or the slot that keeps coming up short. Compare
            suggestions against the cards&apos; oracle text.
          </p>
          <p className="mt-9 w-fit max-w-[34ch] rounded-field rounded-br-control bg-signal px-5 py-3.5 text-lg leading-7 font-semibold text-rail">
            <span className="sr-only">For example: </span>
            What are the best free sacrifice outlets for Meren?
          </p>
        </div>
        <footer className="max-w-[540px] text-sm leading-5 text-white/65">
          <p>
            Card data and images come from{" "}
            <a
              href="https://scryfall.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white underline decoration-white/40 underline-offset-[3px] hover:decoration-white"
            >
              Scryfall
            </a>
            . Cardwise is unofficial Fan Content permitted under the Fan Content Policy. Not
            approved or endorsed by Wizards. Portions of the materials used are property of Wizards
            of the Coast.
          </p>
        </footer>
      </section>
      <main className="flex flex-1 items-center px-5 py-10 sm:px-8 lg:justify-center lg:px-12">
        <div className="mx-auto w-full max-w-[400px]">
          <div className="mb-8 flex justify-end">
            <ThemeToggle />
          </div>
          <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
          <p className="mt-2 text-muted">
            Your Commander questions and saved conversations, together.
          </p>
          <div className="mt-8">
            <SignInForm next={next} notice={notice} mocking={isMocking} />
          </div>
        </div>
      </main>
    </div>
  );
}
