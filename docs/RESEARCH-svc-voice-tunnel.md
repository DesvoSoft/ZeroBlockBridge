# Research: Simple Voice Chat tunnel via Playit.gg (not on roadmap)

Status: exploratory only. No code changes made to the app. Deliberately deferred
(2026-07-08): revisit after the core app and its existing features are polished
and mature. Implementation plan drafted in the "Draft automation flow" below.

## Goal

Let users expose the Simple Voice Chat (SVC) mod's UDP port through Playit.gg,
same as we already do for the Minecraft game port, so voice works without manual
port forwarding.

## Findings

### 1. Playit API has no dedicated SVC tunnel_type

Official `TunnelType` enum (from `playit-cloud/playit-api-java`, an OpenAPI-generated
client — source of truth, not a guess):

```
minecraft-java, minecraft-bedrock, valheim, terraria, starbound, rust, 7days, unturned
```

No `voice`/`svc` value exists. The "MC: Simple Voice Chat" option shown in the
Playit dashboard is a cosmetic preset only — not a distinct API enum.

`tunnel_type` is an **optional** field on `ReqTunnelsCreate`. Required fields are
`port_type`, `port_count`, `origin`, `enabled`.

`PortType` enum: `tcp`, `udp`, `both`.

Source: https://raw.githubusercontent.com/playit-cloud/playit-api-java/master/docs/TunnelType.md,
https://raw.githubusercontent.com/playit-cloud/playit-api-java/master/docs/PortType.md,
https://raw.githubusercontent.com/playit-cloud/playit-api-java/master/docs/ReqTunnelsCreate.md

**Implication**: creating an SVC tunnel via API means calling `tunnels/create` with
`port_type: "udp"`, `tunnel_type: null` (or omitted), `origin.local_port` = whatever
port SVC actually binds to (see below — not fixed at 24454).

### 2. Confirmed real tunnel JSON shape (read-only probe against our own linked account)

Ran a temporary, read-only script (`list_account_tunnels()`, no create/delete) against
the project's existing `config/playit.toml` secret to see the real shape of a live
tunnel record. Script was deleted after the probe; nothing was created or modified.

```json
{
  "id": "8d7efe2d-df69-43cf-adee-c32cff0824c7",
  "tunnel_type": "minecraft-java",
  "port_type": "tcp",
  "port_count": 1,
  "alloc": {
    "status": "allocated",
    "data": {
      "ip_hostname": "225.ip.gl.ply.gg",
      "static_ip4": "147.185.221.225",
      "assigned_domain": "garden-cruise.gl.joinmc.link",
      "port_start": 3196,
      "port_end": 3197,
      "ip_type": "both",
      "region": "global"
    }
  },
  "origin": {
    "type": "agent",
    "data": {
      "agent_id": "4ccae0de-3e29-4a9b-a472-042ab58705b2",
      "local_ip": "127.0.0.1",
      "local_port": 25565
    }
  }
}
```

Only 1 tunnel exists on the account today (the game port). Confirms current
`PlayitManager`/`PlayitApiClient` design is strictly 1 server : 1 tunnel.

### 3. Official SVC + Playit setup (playit.gg/support/svc-minecraft/)

- Dashboard flow: pick agent -> create new "SVC Tunnel" -> Local IP `127.0.0.1`,
  Local Port `24454` (SVC's default, but **user-configurable** in the mod, not
  guaranteed).
- Playit assigns its own public `IP:PORT` (e.g. `147.185.221.181:25732`) — remote
  port is **dynamic**, not 24454.
- Server-side mod config file `config/voicechat/voicechat-server.properties` must
  be hand-edited after the tunnel exists:
  ```
  bind_address=*
  voice_host=<playit_ip>:<playit_port>
  ```
- That file only gets generated after the server has been started once (mod
  bootstraps its config on first boot) and stopped again.
- Mod required on both server AND client or voice doesn't work at all.

Source: https://playit.gg/support/svc-minecraft/

### 4. Current code constraints (as of this investigation)

- `app/services/playit_api.py::create_tunnel()` hardcodes
  `"port_type": "tcp"` and `tunnel_type="minecraft-java"` — needs generalizing
  to accept port_type/tunnel_type as params for a second tunnel.
- `app/core/playit_manager.py` assumes a single `_current_port` /
  `current_address` for the whole lifecycle (start, DNS polling, heartbeat
  restart). A second concurrent tunnel (voice) needs its own tracked address,
  not a replacement of the existing one.
- `_cleanup_stale_tunnels()` only matches tunnel names via regex
  `minecraft-java_[a-z0-9]{4}` — a voice tunnel would need its own naming
  pattern recognized here too, or it'll never get cleaned up as stale.
- Free tier: comment in code references a 4 port-allocation account limit.
  A 2nd tunnel consumes another allocation slot — needs a clear user-facing
  warning if the account is already at its limit (`AgentDisabledOverLimit` /
  port limit errors already partially handled in `_request()`).

## Draft automation flow (not implemented)

1. Detect SVC mod present (jar in `mods/`/`plugins/`) or wait for
   `config/voicechat/voicechat-server.properties` to appear after first boot.
2. Parse that file for the real local voice port (don't assume 24454).
3. Start server once if needed to generate the file, then stop it.
4. Call `create_tunnel(port=<voice_port>, tunnel_type=None, port_type="udp")`
   (requires generalizing `create_tunnel()`).
5. Poll/resolve assigned public `ip:port` (same polling pattern
   `get_or_create_tunnel` already uses).
6. Rewrite `voicechat-server.properties`: set `bind_address=*` and
   `voice_host=<assigned_ip>:<assigned_port>`.
7. Restart server.
8. Extend `_cleanup_stale_tunnels()` regex to also recognize voice tunnel names.
9. Surface both public addresses in UI (game + voice) — today only one
   `current_address` is tracked/displayed.
10. Warn user before creating 2nd tunnel if account is near/at allocation limit.

## Open questions before this becomes a real plan

- Exact allocation limit per plan tier (free vs paid) — need current numbers
  from playit dashboard/account, not assumed.
- Whether `bind_address=*` has any security implication worth flagging to
  users (opens voice port on all local interfaces, not just localhost).
- UI/UX for showing 2 tunnel addresses instead of 1 (design not explored yet).
- Whether other voice/utility mods would benefit from the same generalized
  "extra UDP tunnel" mechanism, i.e. whether to build this SVC-specific or
  as a general secondary-tunnel capability.
