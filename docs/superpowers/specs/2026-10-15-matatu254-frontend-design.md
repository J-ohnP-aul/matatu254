# Matatu254 Frontend Design

## Intent

Create a clear, trustworthy, mobile-first interface for the Smart Matatu Passenger Journey and Stop Notification System. The frontend should reduce uncertainty for passengers, help conductors coordinate alighting requests while managing a trip, and make route and fleet administration straightforward. The map supports these tasks; it is not the only place where important trip information appears.

The system remains a Django application using server-rendered templates and its existing JavaScript modules. Use daisyUI 5 components and semantic color utilities consistently with the project's current CDN-based daisyUI setup. Do not introduce a Tailwind build pipeline as part of this frontend refresh unless existing project configuration requires it.

## Users and core journeys

### Passenger

1. Scan a matatu QR code and see which vehicle and active trip it identifies.
2. Choose an available stage on the assigned route and confirm the destination.
3. Follow a personal live journey until arrival, with the selected destination and next relevant stage kept clear.
4. Receive an approaching-destination notification and finish the journey.

The passenger interface is designed first for a phone in one hand. It should answer “Where am I?”, “Where am I getting off?”, and “How long/how far remains?” without requiring map interpretation. Show GPS freshness so the passenger can distinguish live updates from a delayed location.

### Conductor

1. Open the active trip dashboard and understand whether location sharing is running.
2. Start or stop GPS sharing with a clear action and browser permission feedback.
3. See the next relevant stop, distance/time, and number of passengers alighting.
4. Review destination requests grouped by route stage and use the map as route context.

The dashboard is optimized for quick checks on a phone while the conductor is managing a trip. Location-sharing state must be explicit: not tracking, requesting permission, tracking, signal delayed, and failed. Never imply that passengers have live location when no fresh GPS is being sent.

### Administrator

Administrators manage matatus, QR codes, routes, stages and coordinates, trips, and system configuration. Management pages should use a consistent navigation and page structure, searchable/scan-friendly lists, clear forms, and visible create/edit/QR actions. Destructive or state-changing actions should be explicit and show a success or error result.

## Screen design

### Shared application shell

- Use a consistent Matatu254 brand header and role-aware navigation.
- On small screens, keep primary tasks reachable without a wide desktop navigation bar.
- Use daisyUI cards to group content; buttons for actions; badges/status for trip and GPS state; alerts for approaching stops and errors; progress for journey progress; steps or a vertical route list for route stages; tables for administrator data.
- Use daisyUI semantic colors: primary for the central action, success for healthy/live state, warning for approaching/delayed state, error for failure, and base colors for surfaces. Maintain readable contrast and avoid coloring every element.
- Provide loading, empty, permission-denied, stale-GPS, network-error, and success states. Keep actionable recovery steps next to the message.

### Passenger pages

- **QR entry and destination selection:** identify the vehicle/route before asking for a destination. Show route stages in route order as large touch targets, mark the chosen destination clearly, and provide one unambiguous confirmation action.
- **Live journey:** put destination, next stage, distance, ETA, and GPS freshness in a compact summary above or next to the route map. Keep the route overview and named stages visible by default; offer a recenter/follow action for a closer vehicle view. Make approaching-destination alerts prominent without obscuring controls.
- **History and notifications:** use a consistent, compact list with readable dates, destinations, and notification status.

### Conductor pages

- **Trip dashboard:** put trip identity and GPS-sharing state first. Keep start/stop tracking controls and permission/error feedback adjacent to that state. Place the next-stop alert, alighting count, and ETA before secondary metrics. Present destinations grouped by stage with counts, then the map and live trip details as supporting context.
- **Trip list and notifications:** make active trips easy to distinguish and open; show notification severity and related stop/trip.

### Administrator pages

- **Overview:** concise counts and recent trips with direct links to the relevant management list.
- **Matatus/routes/stages/trips:** consistent list and form layouts, sensible empty states, inline search/filter where the dataset warrants it, and accessible labels/validation.
- **QR management:** show the vehicle identity, active/inactive state, printable QR, and explicit regenerate/toggle controls already supported by the custom management views.

## Interaction and motion

Motion should explain state or spatial relationships and remain subtle. It must not delay an action, make GPS look fresher than it is, or compete with stop alerts.

- Use short 120–220 ms transitions for hover/focus, button feedback, badge/state changes, and opening/closing small panels.
- Use a brief opacity/vertical entrance for a newly appearing approaching-stop alert; do not continuously pulse or shake it. Respect reduced-motion preferences.
- Animate progress changes smoothly and keep the numeric progress available to assistive technology.
- Keep the vehicle marker interpolation that already exists, but guard it against invalid GPS values and retain the last valid position.
- Use skeletons or a small daisyUI loading indicator only while data is actually loading. Avoid indefinite decorative spinners.
- Ensure keyboard focus is visible, controls remain usable without animation, and `prefers-reduced-motion: reduce` disables nonessential motion.

## Visual direction

Use a calm transport-oriented palette built on daisyUI semantic tokens, with Matatu254 green as primary and warm yellow/orange for an approaching stop. Use neutral base surfaces, clear type hierarchy, moderate card borders/radii, and restrained shadows. The same component language should appear across roles, while content density differs: spacious and guided for passengers; compact and action-oriented for conductors and administrators.

## Scope

Included: visual and interaction refresh of existing passenger, conductor, and custom administrator management templates (dashboard, matatu, route, stage, trip, QR, and system configuration pages); responsive layouts; consistent daisyUI components and semantic states; small purposeful transitions; clear GPS/route error states; preserve existing Django routes, permissions, and backend behavior.

Not included without a separate decision: backend/domain feature changes, commercial map-provider procurement, a new frontend framework, changing notification rules or GPS cadence, redesigning Django Admin itself, or adding new product workflows beyond those already present. The current QR regenerate and activate/deactivate actions should be presented clearly; no new QR lifecycle behavior is required.

## Constraints and implementation notes

- Preserve the current Django template architecture, URLs, roles, form submissions, and map JavaScript interfaces.
- DaisyUI 5 is requested. The repository currently has no `package.json` or Tailwind build configuration and includes daisyUI from a CDN on some pages. Reuse that setup consistently unless implementation discovery shows it cannot support a required component.
- Keep passenger and conductor maps on shared components and keep stage labels available in both.
- Design for phone widths first and verify desktop layouts remain balanced.
- Use progressive enhancement: core destination selection, forms, navigation, and trip state must remain understandable if optional animation or map data fails.

## Decisions and assumptions

- Passenger, conductor, and administrator interfaces are all in scope, based on the user's “yes, improve them” response to the three-role design direction.
- Use existing Django/server-rendered pages rather than introducing a SPA.
- Keep the route overview as the initial map state; the user can explicitly recenter to vehicle-follow mode.
- Use subdued motion by default and honor reduced-motion settings.
- Any remaining small visual choices (spacing, breakpoints, icon treatment) are implementation calls as long as they preserve this design and existing behavior.

## Success criteria

- A passenger can identify the vehicle, select a destination, and understand next stage, destination, distance/ETA, and GPS freshness on a phone.
- A conductor can tell whether GPS is actively shared and identify the next stage and alighting count without searching the page.
- An administrator can find and manage a matatu, route/stage, trip, or QR code using consistent page patterns.
- Route/stage context remains accessible on both passenger and conductor maps, and a missing route line or stale GPS has an explicit, understandable state.
- Motion is brief, meaningful, keyboard-compatible, and reduced when the user requests reduced motion.
