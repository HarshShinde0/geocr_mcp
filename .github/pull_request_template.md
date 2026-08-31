## Description

What did you change in the GeoCroissant server or docs. Include the tool or property you touched, for example `create_geocroissant_from_stac`, `geocr:bandConfiguration`, or `config/catalogs.yaml:8`.

## GeoCroissant checks

- [ ] `uv run ruff check src tests` passes
- [ ] `uv run python -m pytest -o addopts='' tests` passes
- [ ] `npx mint validate` in `docs` passes when docs changed
- [ ] Hosted endpoint `https://geocr-mcp-server.onrender.com/mcp` still returns tools when `POST /mcp` is tested

## Type

- [ ] Fix (bbox handling, catalog lookup, band mapping, asset URL preservation)
- [ ] Feature (new `geocr:` property, new tool param, new catalog)
- [ ] Breaking (rename, type change, limit change)
- [ ] Docs only (Mintlify `docs/` for 2026-08-31)

## Related issue

Link the discussion or issue, or note if this is a small fix with no prior discussion.
