import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import Script from "next/script";
import { ThemeProvider } from "@/components/app/theme-provider";
import { publicSans, sourceSerif } from "./fonts";
import { THEME_BOOTSTRAP } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Cardwise", template: "%s | Cardwise" },
  description:
    "Ask about Magic cards for your Commander deck and get answers that link to the cards.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e6ede5" },
    { media: "(prefers-color-scheme: dark)", color: "#15241f" },
  ],
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
      <body>
        <Script id="theme-bootstrap" nonce={nonce} strategy="beforeInteractive">
          {THEME_BOOTSTRAP}
        </Script>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
