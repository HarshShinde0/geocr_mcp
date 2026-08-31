---
name: search-mcp-github
description: Search GeoCroissant proposals, issues, and discussions on GitHub.
license: Apache-2.0
user_invocable: true
arguments:
  - name: topic
    description: Keyword or feature name to search for.
    required: true
---

# Search GeoCroissant on GitHub

This skill searches pull requests, issues, and discussions in `HarshShinde0/geocr_mcp`.

## Where to search

- **Spec and docs.** Read `docs/specification/2026-08-31/schema.mdx` for `geocr:` properties and `docs/registry/about.mdx` for the STAC catalog registry. These are authoritative for current behavior.
- **Pull requests and issues.**
  ```bash
  gh search prs --repo HarshShinde0/geocr_mcp "{topic}"
  gh search issues --repo HarshShinde0/geocr_mcp "{topic}"
  ```
- **Discussions.** No `gh search discussions` command exists. Use GraphQL:
  ```bash
  gh api graphql -f query="query { search(query: \"repo:HarshShinde0/geocr_mcp {topic}\", type: DISCUSSION, first: 20) { nodes { ... on Discussion { title url body author { login } } } } }"
  ```

For past decisions, read merged PRs and closed issues before open ones.

## Query terms

Use both the exact identifier and the plain phrase. Search is not split on camelCase.

- **Identifiers.** `create_geocroissant_from_stac`, `create_geocroissant_from_stac_sources`, `search_eo_datasets`, `geocr:bandConfiguration`, `geocr:spectralBandMetadata`, `geocr:coordinateReferenceSystem`, `GEOCR_CATALOGS_CONFIG`.
- **Phrases.** `"cloud cover"`, `"STAC catalog"`, `"earth-search"`, `"VEDA"`, `"bbox"`, `"band configuration"`.

Skip kebab-case variants.

## When to dig deeper

If a PR looks central to the topic and you need to know why a change was made, read:

- PR comments not tied to a line.
- Review comments on specific lines.
- Review bodies with approve or request-changes.

Each comment has `author_association`. Treat `MEMBER` or `OWNER` as a maintainer.

## Output format

### Pull requests

```markdown
- [#12](https://github.com/HarshShinde0/geocr_mcp/pull/12) - Add Landsat support (Merged 2026-08-15)
  Maps Landsat `eo:bands` center wavelengths from micrometers to nanometers for `geocr:spectralBandMetadata`.
```

### Issues

```markdown
- [#45](https://github.com/HarshShinde0/geocr_mcp/issues/45) - VEDA collection not found (Closed 2026-08-20)
  Live discovery showed a new collection before the snapshot in `config/catalogs.yaml:15` was updated.
```

### Discussions

```markdown
- [#8](https://github.com/HarshShinde0/geocr_mcp/discussions/8) - Bbox order (2026-08-18)
  Confirmed input is `[min_lon, min_lat, max_lon, max_lat]` and `GeoShape box` is `minLat minLon maxLat maxLon`.
```

### Maintainer quotes

Quote directly and add a footnote:

> "Use `geocr:bandConfiguration` on the image field, not on the dataset." [^1]
> — @maintainer

### Key insights

Sum up the main finding and any consensus.

### Footnotes

Add a footnote per quote or claim:

```markdown
[^1]: [#12 review by @maintainer](https://github.com/HarshShinde0/geocr_mcp/pull/12#discussion_r...)
```

## Steps

1. Build search terms (identifier + phrase).
2. Check spec and docs for current `geocr:` behavior.
3. Search PRs and issues with `gh`.
4. Search discussions with GraphQL.
5. Summarize findings with quotes and footnotes.
