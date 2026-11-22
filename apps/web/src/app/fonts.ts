import localFont from "next/font/local";

// Self-hosted (SIL OFL 1.1, licenses next to the files). No runtime requests to Google Fonts.

// Latin subset of the variable font; one file covers every weight we use.
export const schibstedGrotesk = localFont({
  src: "../fonts/SchibstedGrotesk-Variable.woff2",
  variable: "--font-schibsted",
  weight: "400 900",
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
