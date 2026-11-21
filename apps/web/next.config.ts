import type { NextConfig } from "next";
import { staticSecurityHeaders } from "./src/lib/security/csp";

if (process.env.NEXT_PUBLIC_API_MOCKING === "enabled" && process.env.VERCEL_ENV === "production") {
  throw new Error("NEXT_PUBLIC_API_MOCKING must not be enabled in production.");
}

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  cacheComponents: true,
  partialPrefetching: true,
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
