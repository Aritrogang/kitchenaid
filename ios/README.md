# kitchenaid — iOS app

A native **SwiftUI** client (iOS 16+, Swift 5.9+) for the kitchenaid daily
kitchen-assistant API. It talks to the existing FastAPI backend over HTTP:
you set a profile, ask natural-language questions ("what should I make for
dinner?"), and the app renders the assistant's reply, a **meal card**, a
**grocery list**, and a collapsible **agent trace** that showcases the
multi-agent system.

This directory contains **only** the iOS client. The Python backend lives at the
repo root (`kitchenaid/api.py`, run with `uvicorn`).

---

## What's here

```
ios/
├── project.yml                 # XcodeGen spec (generates the .xcodeproj)
├── README.md                   # this file
├── .gitignore
└── Kitchenaid/
    ├── App/
    │   └── KitchenaidApp.swift          # @main entry, TabView (Chat + Profile)
    ├── Models/
    │   ├── Profile.swift                # Profile + Allergen/Diet/Skill enums (Codable)
    │   ├── ChatRequest.swift            # POST /chat request body
    │   └── ChatResponse.swift           # ChatResponse, Meal, GroceryList, GroceryItem,
    │                                    #   Substitution, TraceEvent, HealthResponse
    ├── Networking/
    │   └── KitchenaidAPI.swift          # actor: chat(...) / health(), configurable base URL
    ├── ViewModels/
    │   ├── ChatViewModel.swift          # @MainActor ObservableObject — the source of truth
    │   ├── ChatMessage.swift            # a transcript entry (user / assistant / error)
    │   └── ProfileStore.swift           # UserDefaults persistence (profile + server URL)
    ├── Views/
    │   ├── KitchenTheme.swift           # warm palette + KitchenCard / TagPill
    │   ├── ChatView.swift               # transcript, quick suggestions, input bar, banner
    │   ├── MessageRow.swift             # bubble rendering + ErrorBanner
    │   ├── MealCardView.swift           # name, cuisine, time, $/serving, macros, why, ingredients, flags
    │   ├── GroceryListView.swift        # items (grams + cost), totals, substitutions
    │   ├── TraceView.swift              # collapsible agent → action → detail (ms)
    │   ├── ProfileView.swift            # name, allergies, diet, budget, skill, dislikes, server
    │   ├── FlowRow.swift                # wrapping Layout for tag pills (iOS 16 Layout)
    │   └── Format.swift                 # money / grams / ms formatting
    └── Resources/
        └── Info.plist                   # App Transport Security localhost exception
```

**Architecture:** MVVM. A single `@MainActor ChatViewModel` holds the conversation
and the profile and calls the API with `async/await`. Networking is an `actor`
(`KitchenaidAPI`) so the mutable base URL is isolated. Models are plain `Codable`
structs; the nullable `meal` / `grocery` fields are `Optional` and decode correctly
whether the key is missing or explicitly `null`.

---

## Prerequisites

- **Xcode 15+** (ships the iOS 16 SDK and Swift 5.9).
- The **kitchenaid backend running**. From the repo root:

  ```bash
  pip install fastapi uvicorn
  uvicorn kitchenaid.api:app --reload   # serves http://localhost:8000
  ```

  Sanity check: `curl http://localhost:8000/health` should return
  `{"status":"ok","agents":[...]}`.

---

## Open in Xcode — two paths

You can't build from a bare Sources folder; Xcode needs a project. Pick one:

### Path A — XcodeGen (recommended, one command)

[XcodeGen](https://github.com/yonaskolb/XcodeGen) generates a `.xcodeproj` from
`project.yml`, so the project file is never hand-edited and never drifts from the
sources.

```bash
brew install xcodegen        # if you don't have it
cd ios
xcodegen generate            # writes Kitchenaid.xcodeproj
open Kitchenaid.xcodeproj
```

Then pick an **iPhone Simulator** and hit **Run** (⌘R). Re-run `xcodegen generate`
whenever you add, remove, or rename source files.

> The generated `.xcodeproj` is git-ignored on purpose — `project.yml` is the
> source of truth.

### Path B — Manual (no extra tools)

1. **Xcode → File → New → Project… → iOS → App.**
2. Product Name: **Kitchenaid**, Interface: **SwiftUI**, Language: **Swift**.
   Set the deployment target to **iOS 16.0**. Save it somewhere temporary
   (outside this repo is fine).
3. Xcode creates a starter `KitchenaidApp.swift` and `ContentView.swift`.
   **Delete both** from the project (move to trash).
4. In Finder, open `ios/Kitchenaid/`. Drag the **`App`, `Models`, `Networking`,
   `ViewModels`, and `Views`** folders into the Xcode Project navigator.
   In the dialog, choose **"Create groups"** and check **"Copy items if needed"**
   is *unchecked* if you want to keep editing in place (or checked to copy).
   Ensure the **Kitchenaid** target is checked.
5. **App Transport Security:** either
   - drag `ios/Kitchenaid/Resources/Info.plist` in and set it as the target's
     Info.plist (Target → Build Settings → *Info.plist File*), **or**
   - open your target's **Info** tab and add the key manually (see next section).
6. Select an iPhone Simulator and **Run**.

---

## App Transport Security (the http/localhost gotcha)

iOS **blocks plain `http`** (non-TLS) by default. The backend runs on
`http://localhost:8000`, so the app must opt in. We use the narrow, App-Store-safe
exception `NSAllowsLocalNetworking`, which permits cleartext to `localhost`,
`*.local`, and private LAN addresses **without** disabling ATS for the public
internet.

It's already set in `ios/Kitchenaid/Resources/Info.plist`:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>
</dict>
```

If you took Path B and are editing the Info tab by hand, add:

- **App Transport Security Settings** (dictionary)
  - **Allows Local Networking** = **YES**

For a remote http host that is *not* on your LAN, add an exception domain instead
(replace the host):

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSExceptionDomains</key>
    <dict>
        <key>your.api.host</key>
        <dict>
            <key>NSExceptionAllowsInsecureHTTPLoads</key><true/>
        </dict>
    </dict>
</dict>
```

Prefer HTTPS in production and drop these exceptions entirely.

---

## Pointing the app at the backend

The base URL is configurable and persisted (`@AppStorage`-style, via `UserDefaults`).
Default: **`http://localhost:8000`**.

- **Profile tab → Server**: edit the address and tap **Test connection** (calls
  `GET /health`). A green row means the agents are ready.
- **iOS Simulator:** `http://localhost:8000` works as-is — the Simulator shares
  your Mac's network.
- **Physical device:** `localhost` refers to the *phone*, not your Mac. Use your
  Mac's LAN IP, e.g. `http://192.168.1.20:8000` (find it with
  `ipconfig getifaddr en0`), start uvicorn with `--host 0.0.0.0`, and make sure
  both are on the same Wi‑Fi. `NSAllowsLocalNetworking` already covers private
  LAN IPs.

---

## Using it

1. **Profile tab:** set your name, toggle allergies, pick a diet and skill, set a
   per-meal budget, add dislikes. All of this persists and is sent with every turn.
   A stable `user_id` (UUID) is generated once and reused so the backend remembers
   your taste and last meal.
2. **Kitchen tab:** type a question or tap a quick suggestion:
   - *"what should I make for dinner?"* → assistant message + **meal card**
   - *"what do I need to buy for dinner with rice?"* → meal + **grocery list**
   - *"use up the fridge — I have lentils and carrots"*
   - *"plan my week"* → a plan in the message
   - *"loved it"* / *"that was too spicy"* → feedback (no meal)
3. Expand **the trace** under any reply to see the agent handoffs
   (`Concierge → route → quick_dinner`, timings in ms).

If the backend is unreachable you get a graceful inline error banner and an
offline status dot — no crash.

---

## Notes / assumptions

- The backend also accepts an optional `pantry` object on `/chat`; the app drives
  the "use up the fridge" flow purely through natural-language `query`, which the
  Concierge parses, so `pantry` is intentionally omitted from the request.
- Enum raw values (`tree_nut`, `quick_dinner`, `plan_week`, etc.) match the API
  contract exactly. Unknown future `intent` values decode to a safe `.unknown`
  case rather than failing.
- No third-party Swift dependencies — only Foundation, SwiftUI, and (via
  `URLSession`) the system networking stack.
