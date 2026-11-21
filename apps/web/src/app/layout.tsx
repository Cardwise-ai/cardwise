import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cardwise",
  description: "Ask about Magic cards and get answers that link to the cards.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
