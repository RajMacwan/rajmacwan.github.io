# RouteMock — a realistic GPS route simulator for Android

A personal, no-root mock-location app — a "Flash GO" replacement — whose headline
feature is the one Flash GO lacks: it drives your route at **each road's real speed
limit** and **stops at traffic lights**, instead of gliding at one constant speed
from the highway onto a residential street.

It is built on Android's official, OS-sanctioned mock-location mechanism (the
"Select mock location app" developer setting) — the same mechanism Flash GO and
every no-root fake-GPS app uses. It is intended for testing your own
location-aware apps and flows on your own device.

---

## Why the movement looks real (the part no other app does)

Existing fake-GPS apps (open-source and Flash GO alike) move in one of three ways:
teleport to a point, walk a straight line between two points, or replay a route at
a **single user-set speed**. That last one is your exact complaint: the mock keeps
110 km/h after the route exits the motorway onto a 30 km/h street.

RouteMock fixes this by treating the drive as a physics problem in the **distance
domain** (arc-length `s` along the route):

1. **Per-segment speed limits.** `GraphHopperClient` asks the GraphHopper
   Directions API for the road-snapped polyline **plus** `max_speed` and
   `road_class` for every stretch. So the instant the route changes from
   `motorway` to `residential`, the target speed drops. Missing `maxspeed` tags
   fall back to sensible per-class defaults (`RoadClass`).
2. **Traffic controls.** `OverpassClient` queries OpenStreetMap for
   `highway=traffic_signals`, `stop`, `give_way` and `crossing` nodes within 25 m
   of the route. `RouteRepository` projects each onto the route and decides —
   probabilistically, like a real driver — whether to stop and for how long
   (a red light dwells 10–45 s, a stop sign 2–3 s).
3. **A comfortable motion model** (`MotionSimulator`) turns all of that into a
   1 Hz stream of GPS fixes:
   - a **speed ceiling** at every 2 m = min(road limit, curvature-limited speed);
     tight corners slow you down via `v = sqrt(a_lateral / curvature)`, with a
     backstop cap computed at each real turn vertex from its deflection angle, so
     a sharp intersection is slowed for even when the routing engine draws it with
     a single vertex;
   - a **backward pass** lowers the ceiling *before* every stop/curve so braking
     starts early (`v² = v_next² + 2·a_decel·Δs`) — this is what makes the car
     slow down *on the off-ramp*, not after it;
   - **forward integration in time** accelerates a tracked speed toward the
     ceiling within comfort limits (~1.8 m/s² accelerate, ~2.5 m/s² brake) and
     holds position for each stop's dwell;
   - **smooth, correlated noise** so nothing looks robotic: the speed reading
     drifts up and down over seconds (an AR(1) / Ornstein-Uhlenbeck process, not
     per-tick white noise), and the position wanders a metre or two from
     multipath — most visibly while stopped at a light, where a real phone never
     freezes on one exact coordinate;
   - every emitted fix carries a **consistent** position, `bearing`, and `speed`,
     which is itself a realism signal.

The engine is plain Kotlin with **no Android dependencies** and is covered by JVM
unit tests (`MotionSimulatorTest`) that pin the important behaviors — including the
highway→local slowdown and stopping-at-a-signal.

---

## How the mock reaches other apps

`MockLocationEngine` pushes each fix into **every** location stack an app might read:

- the legacy `LocationManager` `gps` and `network` **test providers**
  (`addTestProvider` / `setTestProviderLocation`), and
- Google Play Services' **Fused Location Provider**
  (`setMockMode(true)` / `setMockLocation(...)`) — what the vast majority of apps
  actually use, and which does **not** automatically inherit the legacy mock.

A foreground service (`MockLocationService`) keeps the 1 Hz loop alive with a
persistent notification and the Android 14+ `location` foreground-service type.

---

## One honest limitation

Making the *trajectory* realistic defeats naive detection (teleporting, impossible
speeds, straight-line movement). It does **not** hide the mock **flag**: on
Android 12+, every fix injected through the test provider or FLP mock mode is
stamped `Location.isMock() == true`, and any app can read that in one line. On a
stock, unrooted phone (your Galaxy Fold 7) there is no supported way to clear it,
and integrity-gated apps (banking, ride-share, some games) additionally use the
Play Integrity API, which can flag a device that has a mock app actively running.

So: this is excellent for **testing your own apps** and for apps that only sanity-
check movement. It is **not** a way to fool an app that specifically checks
`isMock()` or Play Integrity — those see through any mock by design.

---

## Setup

1. **Get a free GraphHopper API key** at <https://www.graphhopper.com/> (Directions
   API). The free tier is plenty for personal use. Paste it into the app once; it's
   remembered.
2. **Open the project in Android Studio** (Giraffe or newer). It will download the
   Gradle wrapper and SDK bits on first sync. Or from the command line with an
   Android SDK installed: `./gradlew :app:assembleDebug`.
3. **Install** the debug APK on your phone.
4. On the phone: **Settings → About phone →** tap *Build number* 7× to unlock
   Developer options, then **Developer options → "Select mock location app"**
   (One UI wording: *"Pick mock location app"*) → choose **RouteMock**.
5. Grant the app **Location** permission when asked, and keep Location Services on.

### Using it

Set a **start** and a **destination** two ways, in any combination:

- **Search bar** (top): type an address ("1600 Amphitheatre Pkwy, Mountain View")
  or raw `lat, lng`, hit search, and pick from the geocoded matches — the pin
  drops exactly on the address. Geocoding uses your GraphHopper key, falling back
  to OpenStreetMap/Nominatim if no key is set.
- **Tap the map**: first tap = start, second tap = destination. Tapped pins are
  reverse-geocoded, so the status line shows the real address, not just numbers.

The first point you set is the start, the second is the destination.

Then choose what to do:

- **Fixed Location** — hold the GPS at the start pin permanently (until you change
  it or Stop). This is the "teleport / stay here" mode; set one point and tap it.
- **Start** — drive the route. You're asked to pick the speed:
  - *Realistic* — you enter a **percent of the posted limit** (100 = drive the
    limit, 110 = 10% over, 90 = under). It still obeys each road's limit as the
    base, slows for corners, and stops at lights. With GraphHopper there is **no
    live traffic** (free-flow + randomized dwells); add a **Mapbox token** (see
    below) to route on the traffic-aware `driving-traffic` profile, whose roads
    and per-segment speeds track Google Maps much more closely.
  - *Fixed speed* — a constant mph you enter, ignoring limits and lights.

When a route finishes, the GPS flips into a **Parked** hold at the destination:
the route/trail clear, the map zooms to a single marker, and the position stays
put until you Stop — or set a new destination and Start to drive on from there.

**Routing source:** enter a **GraphHopper** key for free static routing, and/or a
**Mapbox** token for traffic-aware routing. When a Mapbox token is present it is
used (Google-like, ~100k free requests/month, https://account.mapbox.com/);
otherwise GraphHopper is used. Both keys collapse behind the "API key ✓" button
once saved.
- **Pause / Resume** — during a route, hold the GPS in place, then continue. While
  paused (or even while driving) you can set a **new destination** (tap or search)
  and hit **Start** again to re-route from the current position.
- **Stop** — end everything and hand GPS back to the real provider.

When both ends are set the map **auto-fits** so the whole route is on screen. While
a route plays it shows the **planned route** (blue), a **trail** of where you've
driven (red), **green** start/destination pins, and a **red** marker at the current
(or fixed) GPS position — so you always see where the mock is. The notification
mirrors progress and speed. Open any map/navigation app to see the same movement.

**History** keeps your recent routes and fixed locations — tap **History**, pick
one, and it loads the pins back so you can re-run it with one tap. Your GraphHopper
**API key is saved as you type** and restored on every launch, so you enter it once.

---

## Project layout

```
mock-location-app/
  app/src/main/java/com/rajmacwan/routemock/
    engine/            ← pure-Kotlin, unit-tested, no Android deps
      RouteModels.kt     data classes, road-class speed defaults, tunables
      GeoUtils.kt        haversine / bearing / interpolation
      Polyline.kt        arc-length ↔ lat-lng, point projection
      MotionSimulator.kt the realism engine (ceiling + passes + integration)
    data/
      GraphHopperClient.kt  route + per-segment speed limits
      OverpassClient.kt     traffic signals / stops from OpenStreetMap
      RouteRepository.kt    assembles a ready-to-simulate RoutePlan
    MockLocationEngine.kt   injects fixes into LocationManager + Fused provider
    MockLocationService.kt  foreground service, 1 Hz playback loop
    MainActivity.kt         OSMDroid map UI, start/dest pins, controls
  app/src/test/java/.../MotionSimulatorTest.kt   JVM tests for the engine
```

---

## Tuning

All the knobs live in `SimParams` (in `RouteModels.kt`): acceleration/braking
comfort, lateral-acceleration limit for corners, speed-noise amplitude and
smoothness, GPS position-drift amplitude and smoothness, tick rate, and the random
seed. The road-class default speeds live in the `RoadClass` enum — for
legal accuracy per country, swap that lookup for the
[`osm-legal-default-speeds`](https://github.com/westnordost/osm-legal-default-speeds)
Kotlin library.

Stop-behavior probabilities and dwell ranges are in `RouteRepository.decide(...)`.

## Roadmap ideas (your future add-ons)

- **Favorites & history** (Flash GO parity) — store start/dest pairs.
- **Joystick mode** — manual nudging for non-route spoofing.
- **Offline routing** — self-host OSRM/GraphHopper from an OSM extract to drop the
  API key and work with no network (the `GraphHopperClient` interface stays the same).
- **Multi-waypoint routes** and round trips.
- **GPX import/export** — play back a recorded track, or save a simulated one.
- **Speed-limit / next-light HUD** overlay while driving the route.

## Attribution & licenses of referenced work

- The app skeleton pattern (mock provider, foreground service, joystick) is
  modeled on the MIT-licensed **xiangtailiang/FakeGPS**.
- Road-following behavior was informed by **projectlistick/listick_fake_gps**
  (GPL-3.0) as a *design reference only* — no code was copied.
- Routing: **GraphHopper**. Map & traffic data: **OpenStreetMap** contributors
  (Overpass API). Map tiles: **OSMdroid** / OSM.
