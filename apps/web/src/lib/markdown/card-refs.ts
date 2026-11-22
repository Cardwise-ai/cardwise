/**
 * Card references in answer text: `[[<oracle_id>|<name>]]` (spec §7.4).
 *
 * The plugin only turns matches inside plain text nodes into placeholder spans. Whether a
 * placeholder becomes a button is decided at render time against the message's `cards` event.
 */

export const CARD_REF_ATTR = "data-card-ref";

const ID_PART = String.raw`[^\[\]|\\\n]{1,64}`;
const NAME_PART = String.raw`[^\[\]|\\\n]{1,200}`;
// A backslash can't appear in either part, so escaping the pipe twice is impossible.
const REF_SOURCE = String.raw`\[\[(${ID_PART})\|(${NAME_PART})\]\]`;

const refPattern = new RegExp(REF_SOURCE, "g");

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return uuidPattern.test(value);
}

/**
 * Prepares answer text for the markdown parser:
 * - escapes the pipe inside references so GFM tables don't split a reference into two cells;
 * - while streaming, hides a trailing reference that hasn't been closed yet, so readers never
 *   see half of `[[3f1e…` flash before the rest arrives.
 */
export function prepareAnswerMarkdown(text: string, streaming: boolean): string {
  let source = text;
  if (streaming) {
    const open = source.lastIndexOf("[[");
    if (open !== -1 && source.indexOf("]]", open) === -1 && source.length - open <= 270) {
      source = source.slice(0, open);
    }
  }
  return source.replace(
    new RegExp(REF_SOURCE, "g"),
    (_match, id: string, name: string) => `[[${id}\\|${name}]]`,
  );
}

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hName?: string; hProperties?: Record<string, string>; hChildren?: unknown[] };
}

const SKIP_PARENTS = new Set(["link", "linkReference", "inlineCode", "code"]);
const CODE_NODES = new Set(["inlineCode", "code"]);
const escapedRefPattern = new RegExp(String.raw`\[\[(${ID_PART})\\\|(${NAME_PART})\]\]`, "g");

function splitText(value: string): MdNode[] | null {
  refPattern.lastIndex = 0;
  if (!refPattern.test(value)) return null;
  refPattern.lastIndex = 0;
  const nodes: MdNode[] = [];
  let last = 0;
  for (const match of value.matchAll(refPattern)) {
    const [whole, id = "", name = ""] = match;
    const start = match.index;
    if (start > last) nodes.push({ type: "text", value: value.slice(last, start) });
    nodes.push({
      type: "cardRef",
      children: [{ type: "text", value: name.trim() }],
      data: { hName: "span", hProperties: { [CARD_REF_ATTR]: id.trim() } },
    });
    last = start + whole.length;
  }
  if (last < value.length) nodes.push({ type: "text", value: value.slice(last) });
  return nodes;
}

function walk(node: MdNode): void {
  // Code shows its source literally, so undo the pipe escape prepareAnswerMarkdown added.
  if (CODE_NODES.has(node.type) && node.value) {
    node.value = node.value.replace(escapedRefPattern, "[[$1|$2]]");
    return;
  }
  if (!node.children || SKIP_PARENTS.has(node.type)) return;
  const next: MdNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && child.value) {
      const replaced = splitText(child.value);
      if (replaced) {
        next.push(...replaced);
        continue;
      }
    }
    walk(child);
    next.push(child);
  }
  node.children = next;
}

/** remark plugin: turns `[[id|name]]` in text nodes into card-ref placeholders. */
export function remarkCardRefs() {
  return (tree: MdNode) => {
    walk(tree);
  };
}
