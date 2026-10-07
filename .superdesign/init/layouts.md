# Layouts

## App shell — `app/templates/base.html`

Shared layout for all authenticated pages (and login). Top header with brand + nav; content in `<main>`; optional scripts block.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Telebot{% endblock %}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">Telebot</a>
    {% if user is defined and user %}
    <nav>
      <a href="/">Dashboard</a>
      <a href="/setup">Setup</a>
      <a href="/channels">Channels</a>
      <a href="/posts/new">New post</a>
      <form action="/logout" method="post" class="inline">
        <button type="submit">Log out</button>
      </form>
    </nav>
    {% endif %}
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
  {% block scripts %}{% endblock %}
</body>
</html>
```

### What it renders
- Brand wordmark "Telebot" linking home
- When logged in: horizontal nav — Dashboard, Setup, Channels, New post, Log out
- Centered content column (`main` max-width 960px via CSS)
- No sidebar, no footer
