import type { NextConfig } from "next";
import { staticSecurityHeaders } from "./src/lib/security/csp";

// Previews are the dev environment testers sign in to, so mocks are refused on every Vercel build.
if (process.env.NEXT_PUBLIC_API_MOCKING === "enabled" && process.env.VERCEL) {
  throw new Error("NEXT_PUBLIC_API_MOCKING must not be enabled on Vercel.");
}

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // The persistent build cache (restored by Vercel between builds) kept serving CSS from an
    // older globals.css: it does not invalidate the Tailwind loader output. Builds are small, so
    // every build starts cold. scripts/check-built-css.mjs guards against a regression.
    turbopackFileSystemCacheForBuild: false,
  },
  images: {
    // Card images load straight from Scryfall's CDN; no optimizer in between.
    unoptimized: true,
    remotePatterns: [{ protocol: "https", hostname: "cards.scryfall.io", pathname: "/**" }],
  },
  async headers() {
    return [{ source: "/:path*", headers: [...staticSecurityHeaders] }];
  },
  turbopack: {
    resolveAlias: {
      "msw/browser": { browser: "msw/browser", default: "./src/mocks/msw-browser-ssr.ts" },
    },
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
