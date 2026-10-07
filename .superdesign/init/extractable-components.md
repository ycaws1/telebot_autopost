# Extractable components

## SiteHeader
- Source: `app/templates/base.html` (header.site-header)
- Category: layout
- Description: Top bar with Telebot brand and primary nav
- Extractable props: `activeItem` (string: dashboard|setup|channels|new-post), `showNav` (boolean, default true)
- Hardcoded: Brand text "Telebot", nav labels Dashboard/Setup/Channels/New post/Log out, CSS classes

## SetupBanner
- Source: `app/templates/dashboard.html` (.banner-soft)
- Category: basic
- Description: Soft callout when preview chat or channels missing
- Extractable props: `previewOk` (boolean), `channelsOk` (boolean), `setupHref` (string, default "/setup")
- Hardcoded: copy pattern, link label "Open Setup wizard"

## DataTable
- Source: pattern in `dashboard.html`, `channels.html`
- Category: basic
- Description: Full-width bordered data table used for posts and channels
- Extractable props: none structural (content slots)
- Hardcoded: table border styles from CSS

## PrimaryButton / SecondaryButton / DangerButton
- Source: `app/static/styles.css` (button, .secondary, .danger-btn)
- Category: basic
- Description: Button variants for forms and actions
- Extractable props: `variant` (primary|secondary|danger), `label`
- Hardcoded: colors, radius

## TelegramPhonePreview
- Source: `app/templates/post_form.html` (.tg-phone block)
- Category: basic
- Description: Dark Telegram-style message preview frame
- Extractable props: `channelName`, `caption`, `hasMedia`
- Hardcoded: phone chrome colors, system sans inside mock

## AuthCard
- Source: `app/templates/login.html` (.auth)
- Category: basic
- Description: Centered login form card
- Extractable props: `error` (string|null)
- Hardcoded: Username/Password labels, Sign in button
