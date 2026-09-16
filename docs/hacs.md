# HACS readiness

What is prepared in this repository for HACS, and the state of the submission. The repository is public at https://github.com/ljmerza/irrigation_manager.

Status as of 2026-09-15:

| Step | State |
|---|---|
| Release | [v0.2.0](https://github.com/ljmerza/irrigation_manager/releases/tag/v0.2.0) — full release, `irrigation_manager.zip` attached, `manifest.json` at the zip root with version `0.2.0` |
| Validate workflow | passing (hassfest + HACS action, [run 35047413993](https://github.com/ljmerza/irrigation_manager/actions/runs/35047413993)) |
| HACS default submission | [hacs/default#11022](https://github.com/hacs/default/pull/11022), all 12 checks green, waiting for a HACS maintainer to merge |

Items marked **verify before submitting** came from memory and could not be checked offline; the ones that have since been checked are marked **verified**.

## Prepared in the repository

| Item | File(s) |
|---|---|
| Brand icon (source + renderer) | `assets/icon.svg`, `assets/render_icon.py` |
| Brand PNGs served by Home Assistant | `custom_components/irrigation_manager/brand/icon.png` (256×256), `icon@2x.png` (512×512) |
| HACS metadata | `hacs.json` (`zip_release` + `filename: irrigation_manager.zip`) |
| Validation workflow | `.github/workflows/validate.yaml` — hassfest + HACS action |
| Test workflow | `.github/workflows/tests.yaml` — pytest and panel build via `ljmerza/misc-actions`, ruff (non-blocking) |
| Release workflow | `.github/workflows/release.yaml` — on a `v*` tag: tests, zip, GitHub release via `ljmerza/misc-actions` |
| Stale issues | `.github/workflows/stale.yml` — `ljmerza/misc-actions` reusable workflow |
| Test dependencies | `requirements_test.txt` (pytest-homeassistant-custom-component 0.13.205 → homeassistant 2025.1.4) |
| Frontend lockfile | `frontend/package-lock.json` |
| Lint config | `pyproject.toml` (`[tool.ruff]`) |
| License | `LICENSE` (MIT, same text as orbit-bhyve-ble) |
| Changelog | `CHANGELOG.md` |
| Issue templates | `.github/ISSUE_TEMPLATE/` (bug report with diagnostics, feature request) |
| README | HACS badges and a HACS install section |

## Brand icon

**Finding (verified in the local core checkout, `projects/hass/core` at `a93f0f170da`, 2026-06-21):** Home Assistant 2026.3.0 added the `brands` system integration (commit `2e34d4d3a6a`, PR #163960, 2026-02-25). It serves brand images through the local API and, for custom integrations, reads them from `custom_components/<domain>/brand/` when the folder exists (`Integration.has_branding` in `homeassistant/loader.py`, `_serve_from_custom_integration` in `homeassistant/components/brands/__init__.py`). Allowed names: `icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png` and `dark_` variants; missing ones fall back (`logo.png` → `icon.png`, `icon@2x.png` → `icon.png`, `dark_icon.png` → `icon.png`, …). Without a local file, Home Assistant fetches from the brands CDN.

Consequences:
- On Home Assistant **2026.3 or newer** the shipped icon shows in Settings → Devices & services without any external PR.
- On **older** versions the icon comes only from `brands.home-assistant.io`, which requires a PR to `home-assistant/brands`.
- Whether the **HACS action's brands check** and the **HACS store UI** accept the local `brand/` folder instead of the brands repository: **verify before submitting**.

The icon is a blue water drop with a white sprout, on a transparent background. `assets/render_icon.py` builds both the SVG and the PNGs from one geometry (PNGs drawn with Pillow at 4× and downsampled). The SVG was cross-checked by rendering it in headless Chromium; the result matched the Pillow PNG. Checked for legibility at 24, 32, 48 and 96 px on light and dark backgrounds. Regenerate with `python3 assets/render_icon.py`.

## Workflows

CI/CD uses [`ljmerza/misc-actions`](https://github.com/ljmerza/misc-actions) at `@v2` wherever one of its actions fits.

- **validate.yaml** — `home-assistant/actions/hassfest@master` and `hacs/action@main` (`category: integration`), on push to `main`, PRs, daily and manual runs. misc-actions has no hassfest or HACS action.
- **tests.yaml** — on push to `main`, PRs and manual runs.
  - `pytest`: `ljmerza/misc-actions/actions/python-test@v2` with Python 3.12, `requirements-file: requirements_test.txt` and `prerelease: allow` (homeassistant 2025.1.4 pins `aiohasupervisor==0.2.2b5`, which uv rejects otherwise).
  - `lint`: `ruff check custom_components tests assets` with `continue-on-error: true` — the code currently has unsorted imports (23 `I001` findings with the configured Home Assistant import style). It stays a local job because misc-actions' `ruff-lint` needs a `uv.lock` and also runs `ruff format --check`. Run `ruff check --fix` once, review, then delete the `continue-on-error` line.
  - `frontend`: `ljmerza/misc-actions/actions/npm-build@v2` in `frontend/` (`npm ci` from the committed lockfile, `npm run build`, no pack), then `npx tsc --noEmit` and `git diff --exit-code` on `custom_components/irrigation_manager/www/irrigation-manager-panel.js`. Rebuild and commit the bundle whenever the panel source changes.
- **release.yaml** — trigger: push a tag like `v0.2.0`. Jobs run in order:
  1. pytest, same as above;
  2. build: writes the version from the tag into `manifest.json`, zips the contents of `custom_components/irrigation_manager/` (excluding `__pycache__`/`*.pyc`) so files sit at the zip root, uploads it as an artifact;
  3. `ljmerza/misc-actions/actions/github-release@v2` creates the GitHub release with generated notes and attaches `irrigation_manager.zip`.

  The version bump happens only inside the release job — bump `manifest.json` on `main` as well if the repository should show it.
- **stale.yml** — `ljmerza/misc-actions/.github/workflows/stale-issues.yml@v2`, daily.

`frontend/package-lock.json` was generated offline (`npm install --package-lock-only --offline`) from the installed `node_modules`, so it pins the exact versions that built the committed bundle.

Other action versions (latest majors not checked — **verify before submitting**): `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v7`, `home-assistant/actions/hassfest@master`, `hacs/action@main`.

The test jobs run Home Assistant 2025.1.4 (what the local suite uses), while the integration targets 2026.x at runtime.

## Manual steps

Done:

2. **Checks green on GitHub** — Validate (hassfest, HACS) and Tests both pass on `main`.
3. **Release cut** — `v0.2.0` tagged and pushed; the release workflow produced a full release with `irrigation_manager.zip` attached.
6. **Submitted to the HACS default repositories** — [hacs/default#11022](https://github.com/hacs/default/pull/11022), one line added to the `integration` list. The PR must stay editable and must not be review-requested; HACS closes PRs that request reviews.

Still open:

1. **Make lint blocking**: `ruff check --fix custom_components tests assets`, review the import changes, run the tests, remove `continue-on-error: true` from the `lint` job. 23 `I001` import-order findings remain. This is a house rule, not a HACS requirement.
4. **Test the HACS install** on a test Home Assistant: HACS → Custom repositories → add the repository as Integration → install → restart → add the integration. After #11022 merges the custom-repository step is no longer needed, and the README install section should drop it.
5. **Brands** — **verified not required for the HACS checks**: the `brand/` folder in the integration satisfies the HACS action's brands validation, and the default-repository PR's brands check passed without an entry in `home-assistant/brands`. A PR to `home-assistant/brands` is still needed if you want the icon to show on Home Assistant older than 2026.3.

## HACS default-repository requirements (verified 2026-09-15 against hacs.xyz and the hacs/default checks)

Submission is a PR to [hacs/default](https://github.com/hacs/default) adding `"<owner>/<repo>"` to the `integration` file, sorted with Python's `str.casefold` (`scripts/is_sorted.py` enforces it; `scripts/sort.py` reserializes the whole file, which produces unrelated whitespace changes — insert the single line by hand instead).

The PR must be opened by the repository's owner or a major contributor, from a personal account, with maintainer edits allowed. The PR body has to carry the checklist and three links: the release, the successful HACS action job, and the successful hassfest job.

Requirements the checks enforce:

- Public GitHub repository, not archived, with a description, topics and issues enabled.
- `hacs.json` at the root with at least `name`. `render_readme`, `zip_release` and `filename` are accepted by the HACS action.
- Exactly one integration under `custom_components/<domain>/`; `manifest.json` defines `domain`, `documentation`, `issue_tracker`, `codeowners`, `name` and `version`.
- Brand assets: a `brand/` directory in the integration with at least `icon.png`.
- The HACS action passes with no `ignore` key, and hassfest passes.
- At least one full GitHub release, created after those actions passed. With `zip_release: true`, every release must carry the asset named in `filename`.

The hacs/default PR itself runs: Preflight, Owner, Editable PR, Releases, Removed repository, Existing repository, Hassfest, HACS action, JQ, JSON schema and Sorted.
