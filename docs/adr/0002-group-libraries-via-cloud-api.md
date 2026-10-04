# 0002 — Group libraries are saved via the Zotero cloud API, not the local API

- **Status:** superseded (group saving removed from the GUI)
- **Date:** 2026
- **Context:** The Save-to-Zotero flow initially tried to offer group libraries
  through Zotero's **local HTTP API** (port 23119), adding `list_groups()` /
  `list_group_collections()` and a `group_id` write path. It was built on the
  assumption that `GET /api/groups` works locally (it is a real *web*-API
  route). That assumption was wrong.

- **Facts (verified):** Live probing of a running Zotero showed
  `/connector/ping` → 200 and `/api/users/0/collections` → 200 (personal
  library reads work), but **`/api/groups` → 404 "No endpoint found"** and the
  `/api/groups/{id}/…` routes don't exist either. Zotero's local server exposes
  `/connector/*` endpoints and user-scoped `/api/users/{id}/…` reads, but **no
  route enumerates group libraries**. As a result `list_groups()` always
  returned `[]` and group libraries could never appear in the picker.

  Independently, the Raycast Zotero extension "sees" groups only because it
  reads `zotero.sqlite` directly — not through the HTTP API. That confirms the
  local HTTP API genuinely cannot list groups.

- **Decision (superseded):** Group-library saving was briefly implemented through
  the **Zotero cloud API** (`api.zotero.org`) using a user-supplied API key, while
  the personal library stayed on the local bridge. After testing, the cloud path
  was removed from the GUI: the requested local-popup authorization UX is not
  available for groups, and the app now intentionally offers personal My Library
  only. This ADR remains as historical context for why group saving is absent.

- **Consequences:**
  - The GUI requires no Zotero cloud API key and offers only the personal
    library. To place an item in a group, move/copy it from My Library in Zotero.
  - The old cloud implementation and its API-key setting were removed; no group
    credentials are read or stored by the app.
  - The local bridge remains the single Save-to-Zotero path and its duplicate
    guard applies to My Library.

- **Alternatives considered:** (a) leave group save out entirely; (c) let the
  user type a raw group library id and write via the local `/users/{id}` route
  (works only when the local client has that group loaded, and requires the user
  to look up the id). Cloud-with-key was chosen as it both lists and writes
  groups reliably. See also `CONTEXT.md` ("Group library").
