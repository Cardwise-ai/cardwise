// Stand-in for "msw/browser" in server bundles. The mock worker only ever starts in the browser,
// but client components are also bundled for SSR, where msw/browser has no export.
export function setupWorker(): never {
  throw new Error("The MSW service worker can only start in the browser.");
}
