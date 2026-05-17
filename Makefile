.PHONY: scan patch demo dashboard clean

scan:
	cd target-app && \
	  semgrep --config p/python --config p/security-audit --sarif --output ../semgrep.sarif . && \
	  trivy fs --format sarif --output ../trivy.sarif --quiet .

patch: scan
	python3 src/autopatch.py \
	  --sarif semgrep.sarif trivy.sarif \
	  --repo-root . \
	  --target-root target-app \
	  --llm stub

demo: scan
	python3 src/autopatch.py \
	  --sarif semgrep.sarif trivy.sarif \
	  --repo-root . \
	  --target-root target-app \
	  --llm stub \
	  --dry-run

dashboard:
	python3 -m http.server 8000 --directory dashboard

clean:
	rm -rf .autopatch dashboard/history.json semgrep*.sarif trivy.sarif
