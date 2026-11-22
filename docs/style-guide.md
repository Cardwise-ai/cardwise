# Cardwise style guide

Cardwise is a chat for Commander deckbuilders. The cards are the content. The answer links card
names, and card images and oracle text sit next to it. The interface is a quiet frame for them.

The tokens live in `apps/web/src/app/globals.css`. `apps/web/src/lib/contrast.ts` mirrors them, and
`src/lib/format.test.ts` checks that the two match and that every text pair meets WCAG AA. Components
use tokens only (`bg-panel`, `text-accent`, `rounded-field`). There are no raw hex values in components.

## Idea

- **Light: ultraviolet on cool paper.** Ultraviolet is the deck-box colour. It is the one solid field
  (the rail and the sign-in panel) and the one interactive accent.
- **Dark: the card's black border.** The page and rail are true black (`#000000`, not a tinted
  near-black), so card art sits flush and carries the colour. A single raised neutral (`#141414`) marks
  things you type into or that float.
- Mana colours appear only in mana symbols and colour-identity pips. Every other colour comes from
  the cards themselves.

## Colour

| Token         | Light     | Dark      | Use                                                        |
| ------------- | --------- | --------- | ---------------------------------------------------------- |
| `surface`     | `#f4f2f7` | `#000000` | Page background                                            |
| `panel`       | `#ffffff` | `#141414` | Composer, inputs, dialogs, menus, card panel               |
| `ink`         | `#18141f` | `#f4f2f7` | Body text and headings                                     |
| `accent`      | `#5a2ec0` | `#b79cff` | Links, card references, primary buttons, focus ring        |
| `rail`        | `#24124f` | `#000000` | Sidebar and the sign-in panel                              |
| `signal`      | `#d6c6ff` | `#b79cff` | On the rail only: the wordmark mark, the example question  |

Supporting tokens, tuned per theme:

- `muted`: secondary text.
- `rule` and `rule-strong`: hairlines and field borders. `rule-strong` reaches 3:1 against `panel`.
- `accent-strong`: the primary button's hover state.
- `accent-wash`: your messages and selection.
- `hover` and `placeholder`.
- `action-ink`: text on the accent.
- Rail text: `rail-ink`, `rail-muted`, `rail-rule`, `rail-hover`.
- Errors: `danger`, `danger-strong`, `danger-wash`, `danger-ink`.

Rules:

- All text meets 4.5:1. Add every new text and background pair to the contrast tests.
- Ultraviolet is solid or absent. Don't use gradients, glows, or tinted shadows as decoration.
- Use `signal` only on `rail`. On paper, the accent is `accent`.
- In dark mode, never lift the page off black to "soften" it. Raise individual elements onto `panel`.

## Type

| Role               | Face              | Size / line height          | Weight / tracking |
| ------------------ | ----------------- | --------------------------- | ----------------- |
| Display (hero, new chat) | Schibsted Grotesk | `clamp(36–88px)`, leading 0.94–1 | 750, `tracking-display` (-0.035em) |
| Title (`text-2xl`) | Schibsted Grotesk | 28 / 32                     | 750, `tracking-tight` |
| Heading (`text-xl`, `text-lg`) | Schibsted Grotesk | 22 / 28, 18 / 26        | 750, `tracking-tight` |
| Body (`text-base`) | Schibsted Grotesk | 15 / 24                     | 400, 600 for emphasis |
| Small (`text-sm`)  | Schibsted Grotesk | 13 / 20                     | 400 or 600        |
| Oracle (`text-oracle`) | Source Serif 4 | 16 / 26                     | 400, italic for reminder text |

- Schibsted Grotesk is a compact grotesk with heavy weights. It nods to the bold sans on a card's title
  bar. Source Serif 4 is used only where printed cards use a serif: oracle text, flavour text, and the
  stat line.
- Both fonts are self-hosted under SIL OFL 1.1 in `apps/web/src/fonts`, with their licences beside them.
- Keep the answer measure under about 75 characters.
- Use sentence case everywhere. Don't use all-caps labels or eyebrows above headings.

## Shape

Radius follows role. Never use one radius everywhere.

| Token             | Value         | Use                                                      |
| ----------------- | ------------- | -------------------------------------------------------- |
| `rounded-control` | 6px           | Buttons, inputs, icon buttons, sidebar rows              |
| `rounded-popover` | 10px          | Menus, toasts, tooltips, code blocks                     |
| `rounded-field`   | 14px          | Composer, your messages, example questions, notices      |
| `rounded-sheet`   | 18px          | Dialogs                                                  |
| `rounded-pill`    | full          | Tags, theme toggle                                       |
| `rounded-card`    | printed corner | Card images only                                        |

- A question is a speech shape: `rounded-field` with one tight corner (`rounded-br-control`). Your
  messages, the example questions on a new chat, and the sign-in example all use it. Nothing else does.
- Shadows (`shadow-float`) belong only to layers that float: menus, toasts, dialogs, tooltips. Panels
  and lists are separated by `rule` hairlines or by surface, not by shadows.

## Layout

- The rail is on the left. The conversation sits in a centred column of at most 72ch. The card panel
  opens on the right on desktop and as a sheet on mobile.
- Your messages align right. Answers align left and run the full measure, under a bold accent
  "Cardwise" name.
- Card images sit in a horizontal strip under the answer that cites them.

## Motion

- Motion only answers an action. Sheets slide 16px in 160ms, popovers fade in 120ms, and the caret
  blinks while streaming.
- No entrance animations on page load.
- `prefers-reduced-motion` turns everything off.

## Do and don't

| Do                                                         | Don't                                                       |
| ---------------------------------------------------------- | ----------------------------------------------------------- |
| Name things plainly: "New chat", "Try again", "Ask again"  | Append arrows to buttons ("Continue →")                     |
| Show metadata in labelled rows (card panel)                | Join metadata with middle dots ("Creature · 1/1 · Black")   |
| Use one solid ultraviolet field per screen at most          | Use purple gradients or glows                               |
| Use true black for dark surfaces                           | Substitute `#0b0b0b` or tinted navy for black               |
| Use the speech shape only for questions                    | Wrap every block in an identical rounded card               |
| Use a serif for oracle text                                | Use a serif for headings or UI                              |
| Add new text colours to the contrast tests                 | Add hex values in components                                |
