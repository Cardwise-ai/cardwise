import localFont from "next/font/local";

// Self-hosted (SIL OFL 1.1, licenses next to the files). No runtime requests to Google Fonts.

export const publicSans = localFont({
  src: "../fonts/PublicSans-Variable.woff2",
  variable: "--font-public-sans",
  weight: "100 900",
  display: "swap",
});

export const sourceSerif = localFont({
  src: [
    { path: "../fonts/SourceSerif4-Variable.woff2", style: "normal", weight: "200 900" },
    { path: "../fonts/SourceSerif4-Variable-Italic.woff2", style: "italic", weight: "200 900" },
  ],
  variable: "--font-source-serif",
  display: "swap",
});
