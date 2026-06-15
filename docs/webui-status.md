# Local WebUI Status Page

The first WebUI surface is a generated, read-only HTML status page. It does not
start a server, run agents, call model providers, or pass secrets into Docker.
It only summarizes checked-in demo evidence, live-run proof artifacts, archive
metadata, and exact local commands.

Generate it with:

```bash
python scripts/generate_webui_status.py --output docs/webui-status.html
```

Then open the generated HTML file locally. The page is intentionally static so
the default test suite can verify it without API keys, network access, or a
browser automation dependency.

