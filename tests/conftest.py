"""
Pytest bootstrap: force the credential-free / offline path for the whole suite.

`backend.api` calls `load_dotenv()` at import. With a local `.env` present that
would pull in live HYDRADB/OPENAI credentials, connect to the real backend, and
break the deterministic offline-fixture assertions (and spend real money).

We set the credentials to empty strings *before* anything imports the app.
`load_dotenv()` uses `override=False`, so it will NOT overwrite an already-set
key — even an empty one — keeping the suite credential-free regardless of `.env`.

Live integration tests (tests/test_phase1.py) gate on `HYDRADB_API_KEY` being
truthy, so they skip automatically here. To run them against a real backend,
invoke pytest in a shell where the creds are exported and `.env` is not needed:
    CBOS_OFFLINE_DEMO=0 HYDRADB_API_KEY=... GITHUB_TOKEN=... pytest tests/test_phase1.py
"""

import os

# Only force offline when the caller hasn't explicitly opted into live mode.
if os.environ.get("CBOS_OFFLINE_DEMO", "1").lower() not in ("0", "false", "no"):
    os.environ["CBOS_OFFLINE_DEMO"] = "1"
    # Empty (not unset) so load_dotenv(override=False) leaves them empty.
    os.environ["HYDRADB_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["HYDRADB_ENDPOINT"] = ""
    os.environ["HYDRADB_TENANT_ID"] = ""
