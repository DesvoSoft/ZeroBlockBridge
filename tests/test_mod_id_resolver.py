from app.services.mod_id_resolver import resolve_slug


def test_resolve_known_alias():
    assert resolve_slug("fabric-api-base") == "fabric-api"
    assert resolve_slug("fabric-command-api-v2") == "fabric-api"


def test_resolve_generic_fabric_v_prefix_heuristic():
    assert resolve_slug("fabric-some-new-submodule-v3") == "fabric-api"


def test_resolve_generic_fabric_base_suffix_heuristic():
    assert resolve_slug("fabric-totally-new-base") == "fabric-api"


def test_resolve_unknown_returns_none():
    assert resolve_slug("some-curseforge-only-mod") is None
    assert resolve_slug("spark") is None
