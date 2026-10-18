# Matatu254 frontend notes

## Design decisions

- The frontend stays server-rendered with Django templates and local vanilla JavaScript. It adds no JavaScript framework, CSS framework, build pipeline, or remote UI dependency.
- `static/css/tokens.css` is the design source of truth for the Kenyan green scale, semantic colors, neutral/surface roles, fluid type, 4px-based spacing, radii, elevation, layering, and motion.
- `static/css/app.css` consumes the token roles for the shared app shell and passenger, crew, and management screens. The shared shell lives in `templates/base.html`.
- Passenger navigation uses four bottom tabs: Home, Scan, Trips, and Profile. Crew and management retain role-specific links in the top bar. Safe-area padding supports notched devices and the Android wrapper.
- The public landing screen demonstrates the trip sequence with a working CBD-to-Kawangware destination preview. Its KES 60 fare is explicitly labeled as sample content and should be confirmed before being represented as a real fare.
- Live journey and crew maps are lightweight schematics plotted from stored route-stage coordinates and current GPS coordinates. The route list is the accessible text equivalent; map tiles are not loaded.
- Camera scanning uses the browser `BarcodeDetector` API when available. Manual code entry remains available if camera permission, secure context, or QR detection is unavailable.
- The service worker caches the dedicated public `/offline/` page and same-origin static assets. It fetches navigations from the network and never stores signed-in HTML or CSRF tokens.

## Motion spec

| Interaction | Motion | Reduced motion |
| --- | --- | --- |
| Screen arrival | View Transitions API where available; otherwise a short opacity/translate entrance | Transitions collapse to near-zero duration |
| Bottom navigation | Active marker scales in; bar hides on downward scroll and returns on upward scroll | Bar remains usable with transitions disabled |
| Buttons | Press feedback scales to 0.97; confirmation controls may vibrate for 10ms | Transform feedback is removed with other transitions |
| Journey progress | Progress fill uses `scaleX` with the shared easing and duration tokens | Progress updates immediately |
| QR viewfinder | Scan line moves with transform and opacity | Scan line animation stops |
| Crew counts | A changed count briefly scales and fades | Count changes immediately |
| Alerts and page content | Short opacity and translate entrances | Content remains visible with no travel |

Animations use transform and opacity. JavaScript polling is limited to the trip APIs already used by these workflows and stops when the page is left.

## Adding a screen

1. Add the server-rendered template under the owning Django app and extend `templates/base.html`.
2. Keep existing URL names, view context, form names, CSRF tokens, and ownership checks intact. Add a page title using the `app_title` block and a direct `app_back` link when the screen has a clear parent.
3. Use existing component classes and CSS custom properties from `tokens.css`. Put new visual rules in `static/css/app.css`; do not add inline styles or page-local style blocks.
4. Put behavior in a local file under `static/js/`, load it with Django’s `static` tag, and add a version query when changing it so installed PWAs request the new asset.
5. Render useful server-side empty and validation/error states. For asynchronous data, expose loading, stale, and request-failure states in a polite live region.
6. Preserve keyboard access, visible focus, associated labels, reduced-motion behavior, and a text equivalent for visual maps or status indicators.

## Accessibility and operational notes

- The app shell has a skip link, semantic landmarks, visible focus rings, live regions for connection/GPS/count updates, and labels for camera, search, and forms.
- The scan form keeps a manual fallback for browsers without `BarcodeDetector`.
- Route progress is shown both as a visual route and as an ordered stage list. Stage changes and vehicle arrival alerts are announced without requiring the map.
- In offline mode users see a branded retry screen. Authentication, live maps, and server data still require a connection.
- Static assets are served through Django’s static URL handling, which supports Render’s hashed production filenames. The worker discovers the rendered stylesheet, script, manifest, and icon URLs before caching them.
