# Start the CodebaseOS backend

CodebaseOS answers questions from a local backend at `http://localhost:8000`.

```bash
cd CodebaseOS
make demo       # offline, zero credentials (great to try it out)
# or
make backend    # live — needs HydraDB + OpenAI keys in .env
```

Point at a different URL with the `codebaseos.backendUrl` setting.
