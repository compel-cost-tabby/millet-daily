# Millet Daily

A complete, fail-closed Python system for one faceless Instagram post per day, exclusively about millet grains. It collects only configured approved sources, rejects incidental millet mentions, avoids covered URLs and topics for 90 days, asks Gemini for source-bound structured JSON, validates the result, draws an original 1080 × 1350 JPEG with Pillow, and can publish through Meta's official API.

Automatic publishing is deliberately off by default. No sample or test command contacts Instagram.

## What is included

- Configurable RSS collection with source-domain allow lists, timeouts and per-source isolation
- Configurable, date-bounded PubMed API search built from the millet keyword file
- Millet relevance scoring, Indian-source preference, recency ranking and category rotation
- SQLite URL/topic history and a rolling 90-day repetition check
- Gemini 2.5 Flash structured JSON with evidence-linked claims
- Fail-closed checks for unsupported evidence, invented numbers, untraced factual sentences, prohibited medical language, attribution, caption length and hashtags
- Original Pillow artwork—no downloaded photos or copyrighted news images
- `dry-run`, `approval` and safety-gated `automatic` modes
- Official Meta image-container and publish flow, plus compatible-token refresh command
- A public-GitHub-repository image host using the GitHub Contents API (no extra hosting bill)
- Structured JSON logs, optional webhook failure notices, tests and daily GitHub Actions

## Architecture

```text
approved RSS feeds ─→ domain + millet filter ─→ rank + 90-day history
                                                   │
curated evergreen library ──────────────────────────┘
                         ↓
                Gemini structured JSON
                         ↓
           evidence/safety/schema validation
                         ↓
          Pillow JPEG + draft JSON + SQLite
                         ↓
       dry-run │ human approval │ safety gate
                                      ↓
        GitHub public image URL ─→ Meta API
```

Important files:

- `config/settings.yaml`: schedule, rotation weights and safety windows
- `config/keywords.yaml`: millet names and search/filter terms
- `config/sources.yaml`: enabled feeds, credibility and allowed domains
- `config/branding.yaml`: account name, handle, logo text, palette and footer
- `data/evergreen.yaml`: reviewed fallback topics used when reliable news is unavailable
- `src/millet_news/validation.py`: publication gate
- `.github/workflows/daily.yml`: test-first daily job

## Assumptions and limits

1. RSS titles and summaries are the retrieved source material. Gemini may only assert what that material supports. This intentionally produces no post when the evidence is too thin.
2. A configured feed is not trusted merely because it returns data: every final item URL must remain on its allow-listed publisher domain after the feed response is parsed.
3. The ICRISAT feed is documented but disabled because its server currently returns HTTP 403 to automated feed clients. Re-enable it when the publisher permits RSS readers; the official FAO feed and PubMed API are enabled and verified.
4. The included evergreen entries are starting material, not a permanent editorial database. Review them and add approved topics over time. A reused article URL is rejected even if its angle differs.
5. Gemini's free tier has usage limits and its availability/terms can change. The model name is configurable. Current official documentation lists `gemini-3.5-flash` as a stable model with a free tier.
6. Meta requires a publicly reachable image URL. The included no-extra-cost solution uploads the generated JPEG to `published-assets/` in a **public** GitHub repository. A private repository's raw URL will not work for Meta.
7. Instagram publishing requires a Professional (Business or Creator) account and Meta app configuration. Meta may require app review for accounts the app does not own/manage.
8. GitHub Actions cron is UTC and is not guaranteed to start at the exact minute. The included `03:30 UTC` schedule corresponds to `09:00 Asia/Kolkata`.
9. The GitHub Actions cache carries SQLite history between daily runs. Download the run artifact for backup. GitHub may evict old caches; keeping a durable backup is wise.
10. No system can independently prove arbitrary prose from text using simple string checks. This implementation minimizes risk by requiring exact evidence excerpts, number matching, claim coverage and low-temperature generation. Editorial approval remains the recommended mode for health, policy, market and breaking-news posts.

## Local setup

Install Python 3.11 or newer, then from the repository root:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
pytest
python -m millet_news samples
```

The application reads real secrets from environment variables; it does not automatically load `.env`. In PowerShell, set a value for the current terminal with `$env:GEMINI_API_KEY="..."`. Never commit `.env`.

Generate one local draft without publishing:

```powershell
python -m millet_news run --mode dry-run
```

To test the entire path without Gemini or Instagram:

```powershell
python -m millet_news readiness
```

The mock generator is deliberately explicit and source-bound:

```powershell
python -m millet_news run --mode dry-run --mock-generation
```

## Google Gemini setup (free tier)

1. Open Google AI Studio and create a Gemini API key in a Google Cloud project.
2. Confirm that the project's billing setting and quota match the free tier you intend to use. The repository never enables billing.
3. Store the key as `GEMINI_API_KEY`. The default stable model is `gemini-3.5-flash`; override it with `GEMINI_MODEL` if Google changes availability.
4. Do not enable Gemini search grounding for this workflow. Facts come from the explicitly retrieved approved sources.

## Meta and Instagram setup

Meta changes its screens occasionally, but the required pieces are stable:

1. Convert the Instagram profile to a Professional account.
2. In Meta for Developers, create an app with the **Manage messaging & content on Instagram** use case and select **API setup with Instagram login**. This flow does not require a Facebook Page.
3. Configure the Instagram professional account as an Instagram Tester and accept the invitation from Instagram's Apps and Websites settings.
4. Grant `instagram_business_basic` and `instagram_business_content_publish`. The setup UI may also request the comment, message and insights scopes when those features are enabled.
5. Generate an Instagram User access token and obtain the Instagram professional account ID. This project sends publishing calls to `graph.instagram.com`, as required by Instagram Login.
6. Store the values as `INSTAGRAM_ACCOUNT_ID` and `META_ACCESS_TOKEN`. Set `META_GRAPH_VERSION` to a currently supported version if the default has changed.
7. Token types differ. `python -m millet_news refresh-token` calls Instagram's compatible long-lived-token refresh endpoint. Page access tokens used by some Facebook Login flows follow a different lifecycle; use Meta's documented flow for that token instead.

The publisher creates a single-image media container, polls until processing finishes, then calls `media_publish`. It never uses browser automation, passwords or unofficial Instagram libraries.

## GitHub repository and Actions setup

1. Push this project to a **public** GitHub repository. This is required only because Meta must download each generated image without authentication.
2. In **Settings → Secrets and variables → Actions**, add repository secrets:
   - `GEMINI_API_KEY`
   - `INSTAGRAM_ACCOUNT_ID`
   - `META_ACCESS_TOKEN`
   - optional `FAILURE_WEBHOOK_URL`
3. Add repository variables:
   - `RUN_MODE` = `dry-run` initially
   - `GEMINI_MODEL` = `gemini-3.5-flash`
   - `META_GRAPH_VERSION` = `v26.0` (the version in Meta's current Instagram Login getting-started examples)
   - `AUTOMATION_APPROVED` = `false`
4. Under **Settings → Actions → General → Workflow permissions**, allow read and write permissions. The workflow's short-lived `GITHUB_TOKEN` uploads only the generated public image to `published-assets/`.
5. Run **Daily millet content** manually in `dry-run` mode. Download the artifact, inspect its draft JSON and JPEG, and confirm the test step passed. The workflow first validates the Instagram account ID and token with a read-only API request; it does not publish during this check.
6. Run locally with `approval` mode for the first real draft:

```powershell
python -m millet_news run --mode approval
python -m millet_news approve DRAFT_ID
```

Use `--mock-publish` on the approval command to test status transitions without contacting Meta.

7. Only after the three samples, a Gemini-generated draft, and a Meta test post have been approved, set `AUTOMATION_APPROVED=true` and `RUN_MODE=automatic`. Both values are required for unattended publishing.

## Modes and failure behavior

- `dry-run`: creates validated JSON and JPEG, records history, never publishes.
- `approval`: creates a pending draft; `approve DRAFT_ID` revalidates it immediately before publishing.
- `automatic`: requires `AUTOMATION_APPROVED=true`; validation failure or missing credentials skips/fails before a publish call.
- `--mock-generation`: deterministic test content from source text; it is never selected implicitly.
- `--mock-publish`: returns a fake post ID and never contacts GitHub or Meta.

If no qualifying fresh item exists, the system chooses an unused reviewed evergreen topic with category balancing. If neither exists, it logs `no_eligible_topic` and publishes nothing. Feed failures are isolated. A generation, validation, image-hosting or Meta failure produces a non-zero exit, structured logs and an optional webhook notice.

## Adding feeds and languages

Add an entry to `config/sources.yaml` only after verifying that the publisher is approved, its RSS use is permitted, and every possible destination domain is listed. Redirected/off-domain article URLs are rejected. `config/keywords.yaml` includes the requested English and common Indian grain names. The data model already stores `language`; add translated keyword/branding files and a reviewed language-specific generator instruction before enabling another language.

## Tests

```powershell
pytest
```

The suite covers incidental-mention filtering, topic normalization, URL/topic duplicate prevention, source evidence and medical-language rejection, attribution/hashtag generation, exact JPEG dimensions, and a fully mocked end-to-end publish. Network and Instagram calls are not made by tests.

## Cost and privacy

Python, Pillow, SQLite, feedparser, requests, PyYAML, pytest and GitHub Actions for normal public-repository usage are open-source or available without an added service charge. Gemini's free tier and Meta/GitHub platform limits still apply. ChatGPT Plus is not used by the runtime. Gemini's free-tier data-use terms may differ from paid service terms; do not send confidential material.

## License

MIT. Source publishers retain all rights to their original material. Generated posts must use short attribution and original summaries; do not republish article text or photographs.
