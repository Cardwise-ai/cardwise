import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import { ThemeProvider } from "@/components/app/theme-provider";
import { publicSans, sourceSerif } from "./fonts";
import { THEME_BOOTSTRAP, THEME_COLORS } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Cardwise", template: "%s | Cardwise" },
  description:
    "Ask about Magic cards for your Commander deck and get answers that link to the cards.",
};

export const viewport: Viewport = {
  // The bootstrap script rewrites both theme-color tags to the chosen theme.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_COLORS.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_COLORS.dark },
  ],
  colorScheme: "light dark",
};

// Every page renders per request so Next.js can stamp the CSP nonce from the proxy on its
// scripts. A prerendered shell would ship scripts without one.
export const instant = false;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  await connection();
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${publicSans.variable} ${sourceSerif.variable}`}
    >
      <head>
        {/* A plain inline script blocks first paint; next/script would wait for the runtime. */}
        <script
          id="theme-bootstrap"
          nonce={nonce}
          suppressHydrationWarning
          // eslint-disable-next-line react/no-danger, no-restricted-syntax -- a constant, not user content
          dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }}
        />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
