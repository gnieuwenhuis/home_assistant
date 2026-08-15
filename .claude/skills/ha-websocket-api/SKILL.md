---
name: ha-websocket-api
description: Use when reaching for Home Assistant state that the REST API does not expose - renaming an entity_id or device, reading or writing Lovelace dashboard configs, reading or writing energy dashboard preferences, or checking a sensor's recorder statistic metadata (sum vs mean, a wrong state_class).
---

# The Home Assistant WebSocket API

Part of HA's state is absent from the REST API entirely. The **entity and device
registries**, the **Lovelace dashboard configs**, the **energy dashboard prefs**,
and the **recorder's statistic metadata** live only behind
`http://homeassistant.local:8123/api/websocket`, authenticated with the same
`HOME_ASSISTANT_TOKEN` from `.env` at the repo root: the server opens with
`auth_required`, the client answers `{"type": "auth", "access_token": ...}`, and
every later message carries an incrementing `id` that its reply echoes back.

Load the token into the environment rather than interpolating it into a command,
so the value stays out of transcripts, logs, and shell history. Never `cat` or
`echo` `.env`, never copy the token into a file, a commit, or a message to the
user, and never send it anywhere other than `homeassistant.local`.

Renaming an `entity_id` is the usual reason to reach for it. REST has no endpoint
for one, so an entity keeps whatever id its integration assigned until
`config/entity_registry/update` moves it.

**Read without asking:**

- `config/entity_registry/list` / `config/device_registry/list` — ids, platforms, `disabled_by`, and which device owns each entity
- `search/related` — what references an entity: automations, scripts, scenes, helpers
- `lovelace/dashboards/list` / `lovelace/config` — the dashboards and the cards they store
- `energy/get_prefs` — which sensors feed the energy dashboard
- `recorder/list_statistic_ids` — whether a sensor records `sum` or `mean`, which is how to catch a wrong `state_class`

**Ask the user before any of these**, every time — approval for one does not
carry to the next:

- `config/entity_registry/update` — renames an `entity_id`, and every config file naming the old one stops matching without erroring
- `config/device_registry/update` — renames a device, and with it the friendly names of all its entities
- `lovelace/config/save` — replaces a dashboard's whole config; it is not a merge
- `energy/save_prefs` — replaces the energy dashboard's entire source list

Two things here mislead:

- `search/related` does **not** cover Lovelace. An entity it reports as referenced by nothing can still sit on a card, and renaming it blanks that card with no error anywhere. Scan each dashboard's config separately before trusting a rename is safe.
- aiohttp's default (aiodns) resolver cannot resolve mDNS `.local` names, and fails with `Domain name not found` — which reads like the box being down rather than a resolver limitation. `curl` succeeds on the same host because it uses the system resolver; hand aiohttp a `TCPConnector(resolver=ThreadedResolver())` to do likewise.
- `homeassistant.local` publishes AAAA records beside its A record, and the IPv6 addresses refuse connections intermittently — `Connect call failed`, or `curl` reporting a link-local peer and `http 000`. Pin to IPv4 (`curl -4`, or `family=socket.AF_INET` on the connector) instead of reading it as an outage. A real outage fails on IPv4 too, which is the check worth running before concluding one.

A `401` means the token was revoked or replaced — the fix is a new token from the
HA UI, not a retry. A connection failure means the box is unreachable from this
network; treat live inspection as unavailable and fall back to the test suite
rather than working around it.
