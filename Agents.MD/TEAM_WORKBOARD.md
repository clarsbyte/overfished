# Team Workboard

## Sprint goal

Align Overfished layers so demo work can proceed in parallel with minimal merge conflict.

## In progress

- [ ] Frontend: connect map UI stubs to BFF route contracts (`frontend` -> `api`).
- [ ] API: stabilize request/response schemas for regions, vessels, and agent endpoints.
- [ ] Databricks/ML: define artifact contract consumed by API (table/model URI format).
- [ ] Plugin: define LangChain tool interfaces matching API `AgentBackend`.

## Blockers

- [ ] Assign named owners for each RACI row in root `README.md`.
- [ ] Confirm Databricks workspace host/profile strategy for `databricks/databricks.yml`.

## Next decisions

- [ ] Cache format for upstream API payloads (JSON layout + retention).
- [ ] Versioning strategy for API contracts consumed by frontend.
- [ ] Demo mode toggle behavior for cached vs live upstream calls.
