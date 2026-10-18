# Matatu254

Matatu254 is a Django app for passenger journey tracking, crew trip operations, and fleet and route management.

## Frontend

- **Stack:** Django templates with local CSS and vanilla JavaScript. No JavaScript framework or frontend build step is used.
- **Shared shell:** `templates/base.html` provides the role-aware app bar, passenger bottom tabs, offline notice, and PWA registration.
- **Styles:** `static/css/tokens.css` owns the design tokens. `static/css/app.css` applies them across passenger, crew, and management screens.
- **Scripts:** Local page behavior is in `static/js/`. Templates load scripts through Django’s `{% static %}` tag with a version query so installed PWAs can request updates.
- **PWA:** `manifest.json` defines the install identity and green theme. `sw.js` fetches HTML fresh, caches static assets and the public offline screen, and avoids caching session-specific pages.
- **Motion:** The View Transitions API is used when supported. Other browsers use a transform/opacity fallback. Motion tokens live in `tokens.css`; all non-essential motion respects `prefers-reduced-motion`.
- **Design guide:** See [docs/UI_NOTES.md](docs/UI_NOTES.md) for screen conventions, motion rules, accessibility, and the offline behavior.

Run the Django development server with:

```sh
python manage.py runserver
```
