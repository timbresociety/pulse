# Superseded Prototype Note

This early prototype spec has been superseded by the source-bound market
architecture in `docs/architecture.md`.

Current product behavior is governed by these rules:

- market creation requires a source of record and a MECE object universe
- retrieval is restricted to the market's persisted object universe
- standings, pools, counts, and settlements derive from persisted user activity
- admin access is controlled through `ADMIN_EMAILS`

Keep this file only as a historical pointer for older branches that may still
reference the original path.
