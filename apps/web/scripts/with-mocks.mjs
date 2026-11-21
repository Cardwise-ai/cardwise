// Runs a command with mock mode on: MSW serves the API and a cookie stands in for Supabase.
// Usage: node scripts/with-mocks.mjs next dev
import { spawn } from "node:child_process";

const [command, ...args] = process.argv.slice(2);
if (!command) {
  console.error("Usage: node scripts/with-mocks.mjs <command> [...args]");
  process.exit(2);
}

const child = spawn(command, args, {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, NEXT_PUBLIC_API_MOCKING: "enabled" },
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
