# Theme

## Part 1 — Compact token summary

**Product:** Telebot — personal scheduled Telegram channel poster (admin web UI).

**Palette**
| Token | Value | Role |
|---|---|---|
| `--bg` | `#f6f4ef` | Page background |
| `--ink` | `#1c1a16` | Primary text |
| `--muted` | `#5c574e` | Secondary/hint text |
| `--accent` | `#0f5c4c` | Teal links, primary buttons |
| `--danger` | `#8b2e1f` | Errors, failed rows, danger buttons |
| `--card` | `#fffdf8` | Inputs / surfaces |
| `--line` | `#d9d2c4` | Borders / table rules |
| banner fill | `#efe6d4` | Soft setup banner |

**Atmosphere:** Warm cream paper + soft radial gradient (`#efe8d8` → `--bg`). Editorial / personal-tool feel, not SaaS dashboard chrome.

**Typography**
- UI: `"Source Serif 4", "Iowan Old Style", Georgia, serif`
- Mono (codes): `ui-monospace, monospace`
- Telegram preview mock uses system sans (Apple/Segoe/Roboto)

**Shape / spacing**
- Radius: `4px` controls; `12–16px` Telegram phone mock
- Content width: `960px` centered
- Header padding: `1rem 1.5rem`
- Main padding: `1.5rem`

**No dark mode. No Tailwind.**

## Part 2 — Raw source

Full file: `app/static/styles.css` (see repo; ~255 lines). Key `:root` and body:

```css
:root {
  --bg: #f6f4ef;
  --ink: #1c1a16;
  --muted: #5c574e;
  --accent: #0f5c4c;
  --danger: #8b2e1f;
  --card: #fffdf8;
  --line: #d9d2c4;
}
body {
  margin: 0;
  font-family: "Source Serif 4", "Iowan Old Style", Georgia, serif;
  background: radial-gradient(circle at top left, #efe8d8, var(--bg) 45%);
  color: var(--ink);
  min-height: 100vh;
}
.site-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--line);
}
main { max-width: 960px; margin: 0 auto; padding: 1.5rem; }
```
