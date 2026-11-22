// Fails the build when the emitted CSS is older than src/app/globals.css.
// A stale build cache once shipped CSS without the dark theme (no [data-theme=dark] rules), and
// every check that runs on a fresh CI checkout still passed. Usage: node scripts/check-built-css.mjs
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DARK_BLOCK = /:root\[data-theme="dark"\]\s*\{([^}]*)\}/;

/** Custom properties the dark theme declares in globals.css that the built CSS lacks. */
export function missingDarkTokens(sourceCss, builtCss) {
  const block = DARK_BLOCK.exec(sourceCss);
  if (!block) throw new Error('globals.css has no :root[data-theme="dark"] block.');
  const declared = [...block[1].matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]);
  const compact = builtCss.replace(/\s+/g, "");
  const missing = declared.filter((name) => !compact.includes(`${name}:`));
  if (!/\[data-theme=("?)dark\1\]/.test(compact)) missing.unshift('[data-theme="dark"]');
  if (!compact.includes("color-scheme:dark")) missing.unshift("color-scheme: dark");
  return missing;
}

function cssFiles(dir) {
  return readdirSync(dir, { withFileTypes: true, recursive: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".css"))
    .map((entry) => join(entry.parentPath, entry.name));
}

function main() {
  const root = fileURLToPath(new URL("..", import.meta.url));
  const source = readFileSync(join(root, "src/app/globals.css"), "utf8");
  const files = cssFiles(join(root, ".next/static"));
  if (files.length === 0) {
    console.error("check-built-css: no CSS under .next/static. Run next build first.");
    process.exit(1);
  }
  const built = files.map((file) => readFileSync(file, "utf8")).join("\n");
  const missing = missingDarkTokens(source, built);
  if (missing.length > 0) {
    console.error(
      `check-built-css: the built CSS is stale; it lacks ${missing.join(", ")}.\n` +
        "Delete .next/cache and rebuild.",
    );
    process.exit(1);
  }
  console.log(`check-built-css: ${files.length} CSS file(s) include the dark theme.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
