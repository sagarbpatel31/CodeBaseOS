.PHONY: setup hydradb-test test backend ingest webhooks extension-dev extension-pack dash demo demo-cold break verify cost publish submit

# Install deps, set up venv, install extension dev deps
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
	cd extension && npm install
	cd dashboard && npm install

# Verify HydraDB connection + schema migrations
hydradb-test:
	python -m pytest tests/test_phase1.py -v

# Run the full credential-free test suite (chaos, synthesizer, offline, provenance)
test:
	python -m pytest tests -q

# Start the FastAPI backend (foreground)
backend:
	uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload

# Ingest a repo by URL/path — usage: make ingest REPO=tokio-rs/tokio
ingest:
	cbos ingest $(REPO)

# Expose the backend so real GitHub webhooks reach POST /webhook (live demo).
# 1) make backend   2) make webhooks   3) add the printed URL as a GitHub webhook
#    (content-type application/json; events: push, pull_request, issues).
webhooks:
	@echo "Add  <forwarding-url>/webhook  as a GitHub webhook (push, pull_request, issues)."
	@echo "Then open a PR / push — nodes stream into the graph and the Merkle chain extends."
	ngrok http 8000

# Compile + open VS Code with the extension loaded for debugging
extension-dev:
	cd extension && npm run compile && code .

# Package the .vsix for publishing
extension-pack:
	cd extension && npx vsce package

# Start the dashboard dev server
dash:
	cd dashboard && npm run dev

# One-command offline demo: deterministic clean graph, Merkle green, no creds.
# Backend runs in the background; dashboard in the foreground (Ctrl-C stops it).
demo:
	@echo "CodebaseOS offline demo → http://localhost:3000  (backend :8000, Ctrl-C stops dashboard)"
	CBOS_OFFLINE_DEMO=1 uvicorn backend.api:app --host 0.0.0.0 --port 8000 & \
	cd dashboard && npm run dev

# Clean DB, start everything, ingest the demo repos
demo-cold:
	bash scripts/demo_cold_start.sh

# Drive the chaos endpoints in sequence (tamper → restore → nuclear → revive)
break:
	python3 scripts/chaos.py

# Walk the Merkle chain end-to-end
verify:
	cbos verify

# Print current OpenAI spend
cost:
	cbos cost

# Publish extension to VS Code Marketplace (needs VSCE_PAT in env or .env)
publish:
	cd extension && npx vsce publish -p "$$VSCE_PAT"

# Generate final submission bundle
submit:
	@echo "TODO: implement — scripts/submit.sh"
