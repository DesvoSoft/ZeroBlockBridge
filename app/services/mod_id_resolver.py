from typing import Optional

KNOWN_MOD_ID_ALIASES: dict = {
    "fabric-api-base": "fabric-api",
    "fabric-api-lookup-api-v1": "fabric-api",
    "fabric-command-api-v1": "fabric-api",
    "fabric-command-api-v2": "fabric-api",
    "fabric-networking-api-v1": "fabric-api",
    "fabric-lifecycle-events-v1": "fabric-api",
    "fabric-item-api-v1": "fabric-api",
    "fabric-block-api-v1": "fabric-api",
    "fabric-registry-sync-v0": "fabric-api",
    "fabric-resource-loader-v0": "fabric-api",
    "fabric-screen-api-v1": "fabric-api",
    "fabric-events-interaction-v0": "fabric-api",
    "fabric-rendering-v1": "fabric-api",
    "fabric-entity-events-v1": "fabric-api",
}


def resolve_slug(mod_id: str) -> Optional[str]:
    if mod_id in KNOWN_MOD_ID_ALIASES:
        return KNOWN_MOD_ID_ALIASES[mod_id]
    if mod_id.startswith("fabric-") and ("-v" in mod_id or mod_id.endswith("-base")):
        return "fabric-api"
    return None
