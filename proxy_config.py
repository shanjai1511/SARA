import os
import json

# Proxy list loaded from WEBSHARE_PROXY_JSON environment variable.
# Format: JSON array of [host, port, username, password] tuples.
# Example: [["198.23.239.134","6540","myuser","mypass"]]
# Leave as [] to run without proxies (direct connection).
_env_proxy = os.environ.get("WEBSHARE_PROXY_JSON", "[]")
try:
    webshare_proxy = json.loads(_env_proxy) if _env_proxy.strip() else []
except (json.JSONDecodeError, ValueError):
    webshare_proxy = []
