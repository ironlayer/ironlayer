# Release & Deployment Verification Guide

How to confirm that open-source packages, documentation, and the marketing site are published and live.

---

## 1. PyPI (ironlayer & ironlayer-core)

### How it gets published

- **Trigger:** Pushing a **version tag** (`v*`, e.g. `v0.3.0`) to the repo that runs the workflow.
- **Private repo** (`ironlayer_infra`): `.github/workflows/publish.yml` runs on tag push. Builds with `uv build` (no Rust; core_engine without check_engine native extension).
- **Public repo** (`ironlayer/ironlayer`): `.github/workflows/publish.yml` runs on tag push. Builds **Rust wheels** via maturin (multi-platform) and publishes. Use this repo for releases that include the Check Engine.

### How to verify PyPI

1. **Check that the workflow ran**
   - GitHub → repo → **Actions** → workflow **"Publish to PyPI"**.
   - Find the run for your tag (e.g. `v0.3.0`). Both jobs (`Publish ironlayer-core`, `Publish ironlayer`) should be green.

2. **Check package pages**
   - **ironlayer-core:** https://pypi.org/project/ironlayer-core/
   - **ironlayer:** https://pypi.org/project/ironlayer/
   - Confirm the **version** you tagged appears in "Release history".
   - For `ironlayer-core`, open the version and check **Download files** — you should see wheels (e.g. manylinux, macos, windows) if published from the public repo; only sdist/wheel if from private.

3. **Smoke test install**
   ```bash
   pip index versions ironlayer
   pip index versions ironlayer-core
   pip install ironlayer==<your-version> --dry-run
   ```

4. **Required secrets (for the repo you tag)**
   - GitHub Environment **pypi** with trusted publisher (OIDC) **or** `PYPI_API_TOKEN` in repo/org secrets so `pypa/gh-action-pypi-publish` can upload.

---

## 2. Marketing site & docs (Cloudflare Pages)

### How it gets published

- **Repo:** **Private** only. The public repo does not contain the marketing site (it’s in the sync exclude list).
- **Workflow:** `.github/workflows/deploy-marketing.yml`
- **Trigger:**
  - Push to **main** with changes under **`marketing/`**, or
  - **Manual:** Actions → "Deploy Marketing Site" → "Run workflow".
- **Deploy:** Builds `marketing/` with `npm run build` (Astro), then `wrangler pages deploy dist --project-name=ironlayer-marketing`.

### How to verify the website

1. **Check that the workflow ran**
   - GitHub (private repo) → **Actions** → **"Deploy Marketing Site"**.
   - Latest run should be for your commit that touched `marketing/` or your manual run. Job "Deploy to Cloudflare Pages" should succeed.

2. **Check Cloudflare**
   - Cloudflare dashboard → **Workers & Pages** → **Pages** → project **ironlayer-marketing**.
   - Confirm latest deployment is from the expected branch/commit and has status **Success**.

3. **Check live URLs**
   - Marketing site (and docs): e.g. **https://ironlayer.app** (or the custom domain you use for this project).
   - Click through: **Docs** (e.g. `/docs`, `/docs/quickstart`, `/docs/cli-reference`, `/docs/architecture`) and confirm content and nav match what you expect (including any `ironlayer check` / Check Engine updates).

4. **Required secrets (private repo)**
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`

---

## 3. Documentation (what lives where)

- **In-repo markdown:** `docs/` in the private repo (quickstart, cli-reference, architecture, api-reference, deployment, azure-vm-setup). These are the source for “docs” content; the marketing site’s doc pages are separate Astro files that mirror or link to this.
- **On the web:** The **marketing site** on Cloudflare **is** the public documentation (e.g. ironlayer.app/docs/...). It’s built from `marketing/src/pages/docs/` (and related layouts). So “documentation rendering” = the marketing site deploy; there is no separate docs deploy.

**To confirm docs are “pushed out”:**
- Ensure `marketing/` changes are on **main** so the deploy workflow can run.
- Verify the marketing deploy (steps in section 2), then open the doc URLs above and spot-check.

---

## 4. Sync to public repo (ironlayer/ironlayer)

- **Workflow:** `.github/workflows/sync-to-public.yml` (private repo only).
- **Trigger:** Push to **main** (with path filters; docs are included).
- **Effect:** Copies a filtered tree from private → public; excludes e.g. `marketing/`, internal infra, internal docs.

If you change **docs** or **code** in the **private** repo and want that on the **public** repo and (for code) eventually on PyPI, push to **main** first so sync runs, then tag in the **public** repo for PyPI. If you change the **public** repo directly (e.g. OSS-only features), sync will overwrite those paths on the next run unless you merge those changes back into private first.

---

## 5. Quick checklist after a release

| What | Where to check |
|------|------------------|
| PyPI `ironlayer` | https://pypi.org/project/ironlayer/ — version in release history |
| PyPI `ironlayer-core` | https://pypi.org/project/ironlayer-core/ — version + wheel files |
| Publish workflow | GitHub Actions → "Publish to PyPI" for tag `vX.Y.Z` |
| Marketing deploy | GitHub Actions → "Deploy Marketing Site" (private repo) |
| Cloudflare deploy | Cloudflare Pages → ironlayer-marketing → latest deployment |
| Docs on the web | https://ironlayer.app/docs/... (or your domain) — quickstart, CLI ref, architecture |
| Public repo up to date | Compare main on ironlayer/ironlayer with what you expect after sync |

---

## 6. One-off verification commands

```bash
# PyPI: list published versions
pip index versions ironlayer
pip index versions ironlayer-core

# Optional: install a specific version and run a command
pip install ironlayer==0.3.0
ironlayer --version
ironlayer check --help   # if check engine was included in that release
```

```bash
# Local marketing build (sanity check before relying on CI)
cd marketing && npm ci && npm run build
# Then open marketing/dist/ in a browser or run a local static server.
```
