import requests

def test_forge_url(version, forge_ver):
    url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{version}-{forge_ver}/forge-{version}-{forge_ver}-installer.jar"
    print(f"Testing URL: {url}")
    try:
        resp = requests.head(url, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            # Try without mc_version in the second part? No, usually it's there.
            # Some older versions might be different.
            pass
    except Exception as e:
        print(f"Error: {e}")

test_forge_url("1.20.1", "47.4.10")
test_forge_url("1.21.1", "52.1.0")
