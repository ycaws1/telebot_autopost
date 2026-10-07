# Pages — dependency trees

## `/` Dashboard
Entry: `app/templates/dashboard.html`
Dependencies:
- `app/templates/base.html`
- `app/static/styles.css`

Renders: H1 Dashboard, signed-in line, optional setup banner, Upcoming table (when/channel/caption/view), Recent table (status/error/channel/caption/view+requeue|retry).

## `/login`
Entry: `app/templates/login.html`
Dependencies:
- `app/templates/base.html`
- `app/static/styles.css`

Renders: centered auth form (username, password, Sign in) + optional error.

## `/setup`
Entry: `app/templates/setup.html`
Dependencies:
- `app/templates/base.html`
- `app/static/styles.css`
- inline poll script in template

Renders: 4 steps — Pair (bot username, deep link, 6-digit code), Preview chat candidates, Channel discovery candidates, Done checklist.

## `/channels`
Entry: `app/templates/channels.html`
Dependencies:
- `app/templates/base.html`
- `app/static/styles.css`

Renders: hint, add-channel form, channels table with Verify / Delete / Delete with posts.

## `/posts/new` and `/posts/{id}/edit`
Entry: `app/templates/post_form.html`
Dependencies:
- `app/templates/base.html`
- `app/static/styles.css`
- `app/static/preview.js`

Renders: split layout — left form (channel, schedule+Now, caption, media), right Telegram phone preview mock.

## `/posts/{id}`
Entry: `app/templates/post_detail.html`
Dependencies:
- `app/templates/base.html`
- `app/static/styles.css`

Renders: back link, post meta, caption, media list, status actions (Edit/Cancel/Retry/Requeue).
