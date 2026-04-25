# overfished-langchain-plugin

Optional plugin that satisfies `overfished_api.ports.agent.AgentBackend`.

Install **`overfished-api` first** (same interpreter), then this package:

```bash
cd /path/to/overfished
pip install -e ./api
pip install -e ./plugins/langchain_plugin
# When adding real chains/tools:
pip install -e "./plugins/langchain_plugin[langchain]"
```

Set `AGENT_BACKEND=langchain` when running the API. See [../../README.md](../../README.md).
