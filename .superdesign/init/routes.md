# Routes

Server-rendered FastAPI app. Templates under `app/templates/`. All authenticated pages use `base.html`.

| Path | Template | Summary |
|---|---|---|
| `GET /login` | `login.html` | Username/password sign-in |
| `GET /` | `dashboard.html` | Upcoming + recent posts; setup banner if incomplete |
| `GET /setup` | `setup.html` | Multi-step Telegram pairing wizard |
| `GET /channels` | `channels.html` | Add/list/verify/delete channels |
| `GET /posts/new` | `post_form.html` | Create post + live Telegram phone preview |
| `GET /posts/{id}` | `post_detail.html` | Post status, media list, edit/cancel/retry/requeue |
| `GET /posts/{id}/edit` | `post_form.html` | Same form as new, prefilled |

Routers: `app/routers/auth_routes.py`, `channel_routes.py`, `post_routes.py`, `setup_routes.py`; dashboard in `app/main.py`.
