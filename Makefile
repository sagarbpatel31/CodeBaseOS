.PHONY: setup hydradb-test backend ingest webhooks extension-dev extension-pack dash demo-cold break verify cost publish submit

# Install deps, set up venv, install extension dev deps
setup:
	@echo "TODO: implement — python -m venv .venv && pip install -e '.[dev]' && cd extension && npm install && cd ../dashboard && npm install"

# Verify HydraDB connection + schema migrations
hydradb-test:
	@echo "TODO: implement — .venv/bin/python -m pytest tests/test_phase1.py -v"

# Start the FastAPI backend (foreground)
backend:
	@echo "TODO: implement — .venv/bin/uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload"

# Ingest a repo by URL/path — usage: make ingest REPO=tokio-rs/tokio
ingest:
	@echo "TODO: implement — .venv/bin/cbos ingest $(REPO)"

# Start ngrok tunnel + webhook receiver
webhooks:
	@echo "TODO: implement — ngrok http 8000 & .venv/bin/python -m backend.webhooks"

# Launch VS Code with the extension loaded
extension-dev:
	@echo "TODO: implement — cd extension && npm run compile && code --extensionDevelopmentPath=\$$PWD .."

# Package the .vsix for publishing
extension-pack:
	@echo "TODO: implement — cd extension && npx vsce package"

# Start the dashboard dev server
dash:
	cd dashboard && npm run dev

# Clean DB, start everything, ingest Tokio
demo-cold:
	@echo "TODO: implement — scripts/demo_cold_start.sh"

# Run the chaos test suite
break:
	@echo "TODO: implement — .venv/bin/python scripts/chaos.py"

# Walk the Merkle chain end-to-end
verify:
	@echo "TODO: implement — .venv/bin/cbos verify"

# Print current OpenAI spend
cost:
	@echo "TODO: implement — .venv/bin/cbos cost"

# Publish extension to VS Code Marketplace (run only at hour 42+)
publish:
	@echo "TODO: implement — cd extension && npx vsce publish"

# Generate final submission bundle
submit:
	@echo "TODO: implement — scripts/submit.sh"
