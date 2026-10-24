# Stage 15 — live read-only check of the E-YAY integration (2026-10-24)

Status: **EYAY_LIVE_VERIFIED for E-YAY's real HTTP API code, run from a code-only copy, on E-YAY's own
mock price feed.** Your instruction was to start E-YAY read-only, not to modify the E-YAY project
and to use no trading or portfolio function. All three were kept and proven.

## What was run

1. Recorded a manifest of every file in `C:\dev\clean-e-yay` (49,997 files: path, size, modified
   time). `D:\Clean E-yAy` does not exist on this machine, so there was nothing there to touch.
2. Copied only `apps\api`, `packages`, `config` and `contracts` (353 files, 3 MB) into a throw-away
   folder in `%TEMP%`. **Not copied:** `.env` (so no API keys), `data\runtime` (E-YAY's paper-trading
   state), the dashboard, the workers, the Git history.
3. Checked that every E-YAY module imported from the copy and none from the real tree. Only the
   Python interpreter and its installed packages came from E-YAY's virtualenv, read-only,
   with `PYTHONDONTWRITEBYTECODE=1`.
4. Started **only the HTTP API** (`uvicorn apps.api.main:app`) on `127.0.0.1:9000`. Not started: the
   tick worker, the learning worker, the supervisor and the autostart keeper. The environment forced
   `PAPER_ONLY=true`, `NO_EXECUTION=true`, `PRICE_USE_MOCK=true`, `LLM_MODE=off`, no `.env` loading,
   and redirected all 13 runtime paths into the temporary folder.
5. Ran `scripts\eyay_live_check.py` (Commerce's real adapter) against it, then the browser spec
   `e2e/tests/eyay-live.spec.ts` through the isolated acceptance stack with the connector enabled.
6. Stopped E-YAY and ran the outage check, restarted it to time a cold start, stopped everything,
   compared the manifest again and deleted the copy.

## Results

| Check | Result |
|---|---|
| E-YAY `/system/health` | `paper_safe: true`, `no_execution: true` |
| Adapter state | `ISOLATED_HTTP_READ_ONLY`; regime label valid; 10 asset signals parsed and validated; snapshot id and timestamp present |
| Commerce safety flags | `trade_actions_enabled`, `automatic_execution_enabled`, `finance_writes_enabled` all `false` |
| Addresses Commerce refuses | non-loopback host, embedded credentials, missing port |
| Disabled by default | no network, no data |
| Through Commerce in a real browser | `GET /api/v1/integrations/eyay/market` 200 for a signed-in member (Chromium and WebKit); 401 without a session; `POST`/`PUT`/`DELETE` refused |
| E-YAY stopped | Commerce reports `UNAVAILABLE`, no signals, no error |
| **What E-YAY actually served** | **27 requests, all `GET`, only `/api/v1/system/health` (13) and `/api/v1/regime-report/current` (14); no order, paper-trading or portfolio endpoint was called** |
| **`C:\dev\clean-e-yay` afterwards** | **49,997 files, 0 differences** (path, size, modified time) |

## Read this before relying on it

* **The data was E-YAY's mock feed.** E-YAY labelled it itself (`MOCK_MODE`, "the decision is not
  live"). No real market-data provider or API key was used, so this proves the contract, the safety
  gates and the plumbing, **not** the quality of real market signals. A run on real data would reach
  external market-data services with E-YAY's own keys; I did not do that without your say-so.
* **Cold start is slower than Commerce waits.** E-YAY's first regime report after a start took
  about 7.7 s (it builds the snapshot on demand); later calls take about 90 ms. Commerce's timeout is
  2 s (configurable up to 5 s), so right after E-YAY starts Commerce shows `UNAVAILABLE` until it is
  warm. This fails closed and is correct, but E-YAY should be warmed (or its tick worker running)
  before anyone looks. Nothing was changed for it.
* **Not run inside `C:\dev\clean-e-yay`.** E-YAY writes caches under its data folder (24 mock price
  files appeared in the copy). Running from a copy kept every write out of the real project.
* Your brief named `premium_brief.py` and `world_report.py`. Commerce does **not** use them: the
  integration reads only the two documented endpoints above. Nothing was built on those two modules.
* Commerce has no screen for this yet; the endpoint is API-only.

## Repeat it

```powershell
# copy apps\api, packages, config, contracts to a temp folder, then (all paths outside the project):
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='<copy>'; $env:PAPER_ONLY='true'; $env:NO_EXECUTION='true'
$env:PRICE_USE_MOCK='true'; $env:LLM_MODE='off'; $env:LLM_LOAD_DOTENV='false'; $env:TAVILY_LOAD_DOTENV='false'
# set the 13 *_PATH / *_DIR variables from E-YAY's .env.example to files inside the temp folder
C:\dev\clean-e-yay\.venv\Scripts\python.exe -B -m uvicorn apps.api.main:app --host 127.0.0.1 --port 9000
backend\.venv\Scripts\python.exe scripts\eyay_live_check.py            # warm it first: curl the regime report once
backend\.venv\Scripts\python.exe scripts\eyay_live_check.py --expect-down   # after stopping E-YAY
$env:TOUCHE_EYAY_ENABLED='true'; $env:E2E_EYAY_LIVE='1'   # acceptance stack + npx playwright test eyay-live
```
