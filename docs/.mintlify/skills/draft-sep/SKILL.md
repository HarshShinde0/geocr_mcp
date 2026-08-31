---
name: draft-sep
description: Draft a proposal for a GeoCroissant change in geocr-mcp.
user_invocable: true
arguments:
  - name: idea
    description: Short summary of the proposed GeoCroissant change.
    required: true
---

# Draft a GeoCroissant proposal

This skill guides you through writing a proposal for a GeoCroissant change in `HarshShinde0/geocr_mcp`. It follows `docs/community/sep-guidelines.mdx`. Work in order and do not start the draft until the gate, questions, and research are done.

## Prerequisites

Run from the root of a local clone of `HarshShinde0/geocr_mcp`.

1. Verify `docs/community/sep-guidelines.mdx` exists.
2. Check `git remote -v` points at `https://github.com/HarshShinde0/geocr_mcp.git`.
3. Fetch `main`:

```bash
git fetch origin main
```

Talk to a maintainer in Discord or a Working Group before you draft. A cold proposal is valid but more likely to stall.

## 1. Gate

Decide if the idea needs a written proposal.

### Open a pull request directly (no proposal needed)

- Fix for coordinate transform or bbox handling.
- Docs fix or usage example.
- Add a public STAC catalog endpoint without changing the GeoCroissant schema.
- Patch to the `mlcroissant` validator that does not change the spec.

### Write a proposal

- New `geocr:` schema property (`geocr:coordinateReferenceSystem`, `geocr:bandConfiguration`, `geocr:spectralBandMetadata`, `geocr:spatialResolution`, etc.).
- Change to STAC to GeoCroissant mapping in `src/geocr_mcp_server/eo.py:311` or `src/geocr_mcp_server/spec.py:69`.
- Add or break a FastMCP tool signature (`search_eo_datasets`, `create_geocroissant_from_stac`, `create_geocroissant_from_stac_sources`).
- Change to CRS handling, bbox order `[min_lon, min_lat, max_lon, max_lat]`, or band wavelength units.
- Governance or process change.

When in doubt, ask in Discord.

## 2. Questions

Ask these six before you touch files:

1. **Type?** Standards Track (core schema or tool), Extensions Track (mission-specific), Informational (guide), or Process (governance). Most are Standards Track.
2. **Breaking?** Does it break existing GeoCroissant JSON-LD or `mlcroissant` loaders?
3. **Prototype?** A runnable prototype in `geocr_mcp` is needed before acceptance. Is it ready, in progress, or TBD? It must run, not just be pseudocode.
4. **Where discussed?** Discord thread, Working Group meeting, GitHub Discussion. Save the link for the rationale.
5. **Author and sponsor?** Author `Name <email> (@handle)`. A proposal needs a sponsor to enter draft. If none, use `Sponsor: None` and tag 1-2 maintainers from `MAINTAINERS.md` on the PR.
6. **Security?** Does it touch asset URL handling, `GEOCR_CATALOGS_CONFIG` file reads, path handling in `src/geocr_mcp_server/common.py:472`, or network calls to STAC APIs? State the answer even if it is none.

## 3. Research

Do each step and save the results:

1. **Spec coverage.** Read `docs/specification/2026-08-31/schema.mdx` and `docs/specification/2026-08-31/architecture/index.mdx`. Note what `spec.py:17` `official_context()` already defines and why it is not enough.
2. **Prior art.** Run `/search-mcp-github {idea}` in `HarshShinde0/geocr_mcp`. Look at merged PRs and closed issues first.
3. **Existing proposals.** Search open PRs with the same keywords before you file a parallel one.
4. **Design fit.** Read `docs/community/design-principles.mdx` and `docs/development/roadmap.mdx`. Note which principle the idea supports and whether it fits current priorities.
5. **Schema touch points.** Search `src/geocr_mcp_server/spec.py` and `src/geocr_mcp_server/eo.py` for the types the change would touch. Name them in the draft.
6. **Good examples.** Read two recently merged PRs to see the level of detail expected.

## 4. Draft

Create `docs/proposals/{slug}.md` where `slug` is lowercase with hyphens, trimmed to about 50 characters. Use this outline:

- **Preamble.** Title, Author, Status `Draft`, Type, Date `YYYY-MM-DD`.
- **Abstract.** Short factual summary.
- **Motivation.** What is missing in the current `geocr:` properties or tool today. Use concrete examples.
- **Specification.** Exact JSON-LD vocabulary, `geocr:` property types, and tool signatures. Include `bbox` order and `limit` ranges `1-50` where relevant.
- **Rationale.** Alternatives you tried and why this design was chosen.
- **Backward compatibility.** How existing GeoCroissant files and `mlcroissant` code migrate.
- **Security.** How you handle `contentUrl` schemes `s3://`/`https://`, `GEOCR_OUTPUT_DIR` basename rule, and STAC request limits.

## 5. Checkpoint

Tell the user:

- The path to the draft.
- One sentence per section of what you wrote.

Then ask: open a draft PR now, or stop so they can edit first? Do not continue without a yes.

## 6. Open PR (only if yes)

```bash
git checkout -b proposal/{slug} origin/main
git add docs/proposals/{slug}.md
git commit -m "Proposal: {title}"
git push -u origin proposal/{slug}
gh pr create --repo HarshShinde0/geocr_mcp --base main \
  --title "Proposal: {title}" --body "{one-paragraph summary}" --draft
```

If the branch already exists, reuse it. The PR description should link to the discussion from step 2.
