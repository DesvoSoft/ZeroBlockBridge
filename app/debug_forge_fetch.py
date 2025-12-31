import requests
import json

FORGE_PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"

try:
    resp = requests.get(FORGE_PROMOTIONS_URL, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        promos = data.get("promos", {})
        with open("forge_debug.txt", "w") as f:
            f.write(f"Total promo keys: {len(promos)}\n")
            
            forge_versions = set()
            for key, value in promos.items():
                if "-" in key:
                    mc_ver = key.split("-")[0]
                    forge_versions.add(mc_ver)
                    f.write(f"Key: {key} -> MC Ver: {mc_ver}, Value: {value}\n")
            
            sorted_versions = sorted(list(forge_versions), reverse=True)
            f.write(f"Extracted Versions (Top 20): {sorted_versions[:20]}\n")
    else:
        with open("forge_debug.txt", "w") as f:
            f.write(f"Failed: {resp.status_code}\n")
except Exception as e:
    with open("forge_debug.txt", "w") as f:
        f.write(f"Error: {e}\n")
