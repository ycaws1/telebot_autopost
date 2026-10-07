# Components

Framework: FastAPI + Jinja2 server-rendered HTML (no React/Vue). Styling: single vanilla CSS file `app/static/styles.css`. No component library.

There are no shared React/Vue UI primitives. Shared patterns live as CSS classes used across Jinja templates.

## CSS pattern primitives (from `app/static/styles.css`)

### Buttons
- Primary: `button` (teal fill)
- Secondary: `button.secondary` (outline)
- Danger: `button.danger-btn` (outline danger)
- Inline text action: `.inline button` (transparent, accent text)

### Forms
- `label` block stack
- `input`, `textarea`, `select`
- `.field-row` horizontal input + button
- `.auth` centered login card width
- `.stack` (used on channels form; inherits label stack)

### Feedback
- `.error`, `.ok`, `.flash`, `.flash.ok`, `.flash.error`
- `.banner-soft` setup incomplete callout
- `.hint` muted helper text

### Tables
- `table` full-width with bottom borders
- `.row-failed` danger-tinted failed rows
- `.error-cell` wrapping error column
- `.actions-cell` flex actions (View / Requeue / Retry)

### Layout helpers
- `.layout-split` two-column form + preview (collapses <800px)
- `.back-link` detail-page return link
- `.setup-step`, `.setup-code`, `.candidate-list`, `.checklist` for Setup wizard
- Telegram preview mock: `.tg-phone`, `.tg-chat`, `.tg-msg`, `.tg-media`, album grids

Full CSS source is in `theme.md` / passed via `app/static/styles.css`.
