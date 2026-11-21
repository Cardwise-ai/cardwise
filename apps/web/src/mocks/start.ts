let ready: Promise<void> | undefined;

/** Starts the MSW service worker once. API calls wait on this in mock mode. */
export function startMockWorker(): Promise<void> {
  ready ??= import("./browser").then(async ({ worker }) => {
    await worker.start({ onUnhandledFrame: "bypass", quiet: true });
  });
  return ready;
}
