# Telebot Design System

## Product
Telebot is a personal web admin for scheduling multimedia posts to Telegram channels via a bot. Single-admin tool: login, setup wizard, channels, compose/schedule posts, dashboard queue.

## Jobs to be done
- See what’s upcoming and what failed/posted
- Pair bot + discover preview DM and channels without hand-copying IDs
- Compose caption + media with a faithful Telegram preview
- Requeue/retry without digging through settings

## Key pages
Dashboard · Setup · Channels · New/Edit post · Post detail · Login

## Visual direction — Telegram-native (target redesign)
Inspired by Telegram Desktop / Telegram Web A — **not** the current warm cream/serif look.

### Color
| Role | Value | Notes |
|---|---|---|
| App bg | `#0e1621` | Deep TG blue-black |
| Panel / sidebar | `#17212b` | Secondary surfaces |
| Chat / content | `#0e1621` / `#182533` | Message areas |
| Elevated card | `#242f3d` | Inputs, modals |
| Hairline | `#0f1a24` / `#2b5278` borders | Subtle separators |
| Primary accent | `#2AABEE` | Telegram blue — links, primary CTA, active nav |
| Accent hover | `#229ED9` | |
| Text primary | `#F5F5F5` / `#E4ECF2` | |
| Text secondary | `#708499` | Hints, meta |
| Danger | `#E53935` | Failed status |
| Success | `#4FAE4E` | Posted / OK |
| Warning soft | `#3d3420` bg + `#f0b429` text | Setup incomplete banner |

### Typography
- UI: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Mono for codes/IDs: `ui-monospace, SFMono-Regular, Menlo, monospace`
- No serif display faces

### Shape & density
- Radius: 8–12px panels; 6px controls; pills sparingly for status chips
- Dense but readable tables; 14–15px body
- Top app bar (not marketing hero); optional left rail for nav on desktop
- Max content ~1040px or fluid with padded panels

### Components
- **Header**: dark bar, wordmark “Telebot”, nav items with blue active underline/pill
- **Status chips**: pending (blue), posted (green), failed (red), cancelled (muted)
- **Tables**: zebra or row hover on `#17212b`; no heavy card borders
- **Buttons**: filled blue primary; ghost secondary; red outline danger
- **Telegram preview**: keep existing phone mock language (dark bubble `#182533`, author `#6ab2f2`) — it already matches TG

### Motion
- Subtle 150ms hover on rows/buttons; no glow/neon
- Setup steps: quiet progress indicator, not wizard fireworks

### Do / Don’t
- Do feel like Telegram’s own settings/chat list
- Don’t use purple gradients, cream paper, or serif editorial styling
- Don’t invent a logo mark — text wordmark “Telebot” is fine

## Implementation note
Production app is Jinja2 + vanilla CSS. Designs may use Tailwind in Superdesign drafts; implement later by mapping tokens into `app/static/styles.css`.
