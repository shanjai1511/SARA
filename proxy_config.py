import os
import json

# Proxy list is loaded exclusively from the WEBSHARE_PROXY_JSON environment variable.
# Format: JSON array of [host, port, username, password] tuples.
# Example: [["198.23.239.134","6540","myuser","mypass"]]
# See .env.example for full documentation.
_env_proxy = os.environ.get("WEBSHARE_PROXY_JSON")
if _env_proxy:
    webshare_proxy = json.loads(_env_proxy)
else:
    raise EnvironmentError(
        "WEBSHARE_PROXY_JSON environment variable is not set. "
        "Copy .env.example to .env and fill in your proxy credentials."
    )
