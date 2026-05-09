# ECO-00: Playit.gg API Integration Reference Analysis

This document outlines the architecture, flow, and best practices extracted from the reference implementation (`auto-mcs`) for integrating the Playit.gg API. This will serve as the foundation for the Phase 3 `ECO-04` task in ZeroBlockBridge (ZBB).

## 1. Authentication Management & Secret Key Persistence

### Linking Flow (Third-Party Auth)
- The Playit API offers a third-party setup wizard. The user visits a URL like:
  `https://playit.gg/account/setup/wizard/new-account/third-party/third-party-code?partner=auto-mcs`
- This provides the user with an **`account_setup_code`**.
- The reference implementation uses an intermediate "worker" server (`https://playit.auto-mcs.com/link`) to exchange this `account_setup_code` for an `agent_secret_key`. This is because exchanging the setup code for a secret key might require partner-level credentials or CORS bypasses that the desktop client cannot securely hold. ZBB may need a similar proxy or to investigate if the public API allows direct exchange without a partner token.

### Persistence (`playit.toml`)
- The `agent_secret_key` is persisted locally in a `playit.toml` file inside the playit binary directory.
- The format is a simple TOML key-value pair:
  ```toml
  secret_key = "secret-key-goes-here"
  ```
- The Playit CLI agent natively supports reading this file when launched with the `--secret_path` flag:
  `playit.exe -s --secret_path "playit.toml"`
- This completely unifies the programmatic API state and the CLI agent state. Both the HTTP API (using the secret key in headers) and the background process (reading the TOML) share the identical identity.

## 2. API Interaction: JSON Mapping, Error Handling & Timeouts

### Request Formatting
- The API base URL is `https://api.playit.gg`.
- Authentication is passed via headers: `Authorization: agent-key {secret_key}`.
- All requests are executed via `requests.Session()` to reuse TCP connections, improving latency for repeated polling or operations.

### JSON Response Mapping
- The playit API typically responds with a standard wrapper:
  ```json
  {
    "status": "success",
    "data": { ... }
  }
  ```
- The implementation maps `tunnels/list` into object representations (`Tunnel` class) that keep track of vital networking data:
  - `status`: Derived from `tunnel_data['alloc']['status']`. Tunnels can be `pending` until Playit assigns infrastructure.
  - `port`, `host`: Derived from `tunnel_data['origin']['data']['local_port']`.
  - `domain`, `remote_port`: Derived from `tunnel_data['alloc']['data']['assigned_domain']`.
  - `protocol`: Mapped from `port_type` (e.g., `tcp`, `udp`, `both`).

### Error Handling & Timeouts
- **Timeouts**: The link flow explicitly uses a `timeout=20` argument. Network timeouts raise `RuntimeError` wrapped around `requests.RequestException`.
- **API Errors**: HTTP errors (status code >= 400) are parsed to find the exact error message within keys like `error`, `message`, or `detail`.
- **Tunnel Failbacks**: The API sometimes fails to return `origin.data.local_port` for existing tunnels. The reference mitigates this using a local cache (`tunnel-cache.json`). If the API omits the local port, it falls back to the cache. If it's missing from both, the tunnel object self-deletes to clear corrupted state.

## 3. Agent and Tunnel Creation Flow

### Initialization
1. Ensure the binary is installed.
2. Read the `secret_key` from the `playit.toml` config file.
3. Fetch the `agent_id` via the `agents/rundata` endpoint.
4. Call `proto/register` to report the agent's software version to the API. This returns a `proto_key`.
5. Retrieve and map all existing tunnels (`tunnels/list`).

### Tunnel Creation (`tunnels/create`)
1. **Validation**: Check if the account has reached its tunnel limit (e.g., max 4 tunnels). If the limit is exceeded, the implementation recycles the oldest unused tunnel automatically before creating a new one.
2. **Payload Construction**:
   - Assign a name (e.g., `minecraft-java_abcd`).
   - Define type (`minecraft-java` for TCP, `minecraft-bedrock` for UDP).
   - Set the origin data pointing to `127.0.0.1:{local_port}` and tie it to the `agent_id`.
3. **Polling for Assignment**:
   - The API immediately returns an `id` but the tunnel `status` will be `pending`.
   - The system polls `tunnels/list` up to 15 times (1 second intervals) until the `status` changes from `pending` to an active state, allowing it to extract the final `assigned_domain` and `remote_port`.

### Agent Lifecycle
- The background agent is spawned via `subprocess.Popen` in detached mode.
- Multiple Minecraft servers might share the same agent. Thus, tunnels have an `in_use` flag.
- When a server shuts down, its tunnel is marked `in_use = False`. The agent process is killed **only if** no other tunnels are currently flagged as `in_use`. This allows running multiple servers behind one agent process without conflict.

## Actionable Takeaways for ZBB (Phase 3 - ECO-04)
- **Drop Web Scraper**: Move entirely away from the `claim_url` CLI console scraping. Use the `account_setup_code` flow for a clean UI integration.
- **Implement Caching**: Replicate the `tunnel-cache.json` logic. It proves essential for bridging gaps when the Playit API is slow or drops metadata.
- **Agent Orchestration**: Adapt the `in_use` reference counting mechanism to integrate seamlessly with our new `ZBBManager` and `EventBus`. The manager should start the agent process if any server requests a tunnel, and stop it only when 0 servers require it.
- **Error Robustness**: Build a dedicated API client wrapper to handle HTTP >= 400 responses, parsing standard Playit error structures.
