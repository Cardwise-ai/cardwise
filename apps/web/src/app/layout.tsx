import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import { publicSans, sourceSerif } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Cardwise", template: "%s | Cardwise" },
  description:
    "Ask about Magic cards for your Commander deck and get answers that link to the cards.",
};

export const viewport: Viewport = {
  themeColor: "#e6ede5",
};

// Every page renders per request so Next.js can stamp the CSP nonce from the proxy on its
// scripts. A prerendered shell would ship scripts without one.
export const instant = false;

export default async function RootLayout({ children }: LayoutProps<"/">) {
  await connection();
  return (
    <html lang="en" className={`${publicSans.variable} ${sourceSerif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
