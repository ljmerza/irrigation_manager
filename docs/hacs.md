# HACS readiness

What is prepared in this repository for HACS, and what has to be done by hand. Nothing has been pushed: the project is not a git repository yet, and no GitHub repository, release or pull request exists.

Items marked **verify before submitting** come from memory of HACS / GitHub behaviour and could not be checked offline.

## Prepared in the repository

| Item | File(s) |
|---|---|
| Brand icon (source + renderer) | `assets/icon.svg`, `assets/render_icon.py` |
| Brand PNGs served by Home Assistant | `custom_components/irrigation_manager/brand/icon.png` (256×256), `icon@2x.png` (512×512) |
| HACS metadata | `hacs.json` (`zip_release` + `filename: irrigation_manager.zip`) |
| Validation workflow | `.github/workflows/validate.yaml` — hassfest + HACS action, on push to `main`, PRs, daily, manual |
| Test workflow | `.github/workflows/tests.yaml` — pytest (Python 3.12, `requirements_test.txt`), ruff (non-blocking), panel type check + build + bundle comparison |
| Release workflow | `.github/workflows/release.yaml` — on a published release: version from tag into `manifest.json`, zip the integration, attach `irrigation_manager.zip` |
| Test dependencies | `requirements_test.txt` (pytest-homeassistant-custom-component 0.13.205 → homeassistant 2025.1.4) |
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

- **validate.yaml** — `home-assistant/actions/hassfest@master` and `hacs/action@main` (`category: integration`).
- **tests.yaml**
  - `pytest`: Python 3.12, `pip install -r requirements_test.txt`, `python -m pytest -q -p no:cacheprovider`.
  - `lint`: `ruff check custom_components tests assets` with `continue-on-error: true` — the code currently has unsorted imports (23 `I001` findings with the configured Home Assistant import style). Run `ruff check --fix` once, review, then delete the `continue-on-error` line.
  - `frontend`: Node 22, install, `npx tsc --noEmit`, `npm run build`, then `git diff --exit-code` on `custom_components/irrigation_manager/www/irrigation-manager-panel.js`. There is no `frontend/package-lock.json` yet (dependencies were copied from tracking-number-card's `node_modules` offline), so the job falls back to `npm install` and **skips the bundle comparison with a warning** until a lockfile is committed.
- **release.yaml** — trigger: release published. Accepts tags `0.2.0` or `v0.2.0` (fails otherwise), writes the version into `manifest.json` with `jq`, zips the contents of `custom_components/irrigation_manager/` (excluding `__pycache__`/`*.pyc`) so files sit at the zip root, attaches the zip with `softprops/action-gh-release@v2`. The version bump happens only inside the release job — commit the matching version to `main` as well if you want the repository to show it.

Action versions used (the same ones as in `orbit-bhyve-ble`'s workflows; current latest majors not checked — **verify before submitting**): `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `home-assistant/actions/hassfest@master`, `hacs/action@main`, `softprops/action-gh-release@v2`.

CI caveat: the test job runs Home Assistant 2025.1.4 (what the local suite uses), while the integration targets 2026.x at runtime. Installing `homeassistant==2025.1.4` with plain pip may hit its exact pre-release dependency pins (orbit-bhyve-ble notes `aiohasupervisor==0.2.2b5` needed `prerelease: allow` under uv) — **verify on the first CI run**.

## Manual steps

1. **Create the GitHub repository** `ljmerza/irrigation_manager` (public). The name must match `manifest.json` (`documentation`, `issue_tracker`) and the README badges. Add a description and topics such as `home-assistant`, `hacs`, `homeassistant-custom-component`, `irrigation`.
2. **Initialise git and push** `main`. `.gitignore` already excludes `frontend/node_modules/`, `__pycache__/` and `.pytest_cache/`.
3. **Commit a frontend lockfile**: `cd frontend && npm install` (needs network) and commit `package-lock.json`, so CI installs pinned versions and the bundle comparison runs. Rebuild and commit the bundle if the build output changes.
4. **Make lint blocking**: `ruff check --fix custom_components tests assets`, review the import changes, run the tests, remove `continue-on-error: true` from the `lint` job.
5. **Get the checks green** on GitHub: Validate (hassfest, HACS) and Tests. Fix anything hassfest reports (translations, services, manifest).
6. **Cut a release** (e.g. `v0.2.0`, marked as a full release, not a pre-release) and confirm `irrigation_manager.zip` is attached and contains `manifest.json` at its root.
7. **Test the HACS install** on a test Home Assistant: HACS → Custom repositories → add the repository as Integration → install → restart → add the integration.
8. **Brands** — if the HACS brands check fails or you support Home Assistant older than 2026.3: open a PR to `home-assistant/brands` adding `custom_integrations/irrigation_manager/icon.png` and `icon@2x.png` from `custom_components/irrigation_manager/brand/` (**verify before submitting** the current brands repository rules for custom integrations).
9. **Submit to the HACS default repositories** once the above pass (**verify before submitting** the current process; historically a PR to `hacs/default` adding the repository to the `integration` list).

## HACS default-repository requirements (from memory — verify before submitting)

- Public repository on GitHub, not archived, with a description, topics and issues enabled.
- `README.md` describing the integration; `hacs.json` at the repository root with at least `name`.
- Exactly one integration under `custom_components/<domain>/`; `manifest.json` includes `domain`, `name`, `version`, `documentation`, `issue_tracker` and `codeowners`.
- The HACS action passes (repository structure, information, brands, releases).
- hassfest passes.
- At least one GitHub release (full release, not only a tag).
- Brand images available where the HACS brands check expects them (see Brand icon above).
- With `zip_release: true`, every release must carry the asset named in `filename`; the zip's contents are extracted into `custom_components/irrigation_manager/`.
