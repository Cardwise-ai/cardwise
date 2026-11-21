# External services setup

Everything Cardwise needs outside this repo, in the order to set it up. Every service here is on a free plan and none asks for a payment card.

Secrets go straight from a dashboard into Vercel, GitHub or your local `.env`. They never go in chat, in commits or in this file.

## How the pieces connect

| Service | Plan | Connected to the repo by | Deploys |
|---|---|---|---|
| Supabase `cardwise-prod` | Free | Supabase GitHub integration | Migrations and storage buckets on every push to `main` |
| Supabase `cardwise-dev` | Free | Supabase GitHub integration | Migrations and storage buckets on every push to `dev` |
| Vercel `cardwise-web` | Hobby | Vercel GitHub app | Web app: production from `main` (prod database), a preview for every other branch and PR (dev database) |
| Vercel `cardwise-api` | Hobby | Vercel GitHub app | API, once the endpoints exist (Line C) |
| Google AI Studio | Free tier | API key in Vercel | n/a |
| OpenRouter | Free models | API key in Vercel | n/a |
| GitHub Actions | Free | This repo | CI now; ingest, backups and live evals later |

**Branches:** feature branches merge into `dev` (squash), which deploys to `cardwise-dev`. A release is a PR from `dev` into `main` (merge commit, so the two branches keep one history), which deploys to `cardwise-prod`. Every migration therefore runs on the hosted dev database before prod. A hotfix merged straight to `main` must be merged back into `dev`.

| Branch | Supabase | Vercel | GitHub environment | Merge method |
|---|---|---|---|---|
| `dev` (default) | `cardwise-dev` | Preview | `dev` | squash |
| `main` | `cardwise-prod` | Production | `prod` | merge commit |

Both branches are protected by repo rulesets: changes only through PRs with green CI (`python`, `db`, `web`, `secrets`, `audit`), no force pushes, no deletion.

**Why the Supabase GitHub integration instead of a deploy workflow:** on every plan, the integration applies new migrations and creates the storage buckets declared in `supabase/config.toml` when its production branch changes. No access token, project ID or database password has to live in GitHub. Preview branches (a database per PR) are a paid add-on, so we don't use them. CI already tests every migration against a fresh local Supabase.

The integration does not deploy Auth or API settings by default. Those are set once in the dashboard (steps 5 and 6).

## 1. Accounts and identity

1. Make sure `yhaliwa1@gmail.com` (the git commit email) is a verified email on your GitHub account: github.com → Settings → Emails. Vercel Hobby deploys a private repo only for commits by the account owner, and it matches by this email.
2. Create these accounts, all with "Continue with GitHub":
   - supabase.com
   - vercel.com (choose **Hobby**, personal use)
   - openrouter.ai
3. Use a Google account for Google AI Studio (step 9). A separate Google account for Cardwise keeps it apart from your personal data.

## 2. Repo protection

The repo is public, so GitHub Free enforces rulesets. Settings → Rules → Rulesets has `dev` and `main` as described above. Settings → General → Pull Requests allows squash and merge commits (each branch's ruleset narrows it to one), and deletes head branches after merge.

## 3. Supabase organization and projects

1. supabase.com/dashboard → New organization: name `Cardwise`, plan **Free**.
2. New project, twice:

   | Field | Production | Development |
   |---|---|---|
   | Name | `cardwise-prod` | `cardwise-dev` |
   | Region | East US (North Virginia) | the same |
   | Database password | Generate. Save it in a password manager. | Generate a different one. |
   | Enable Data API | On (only `public` is exposed, and we use no tables there) | On |
   | Automatically expose new tables | **Off** | **Off** |
   | Enable automatic RLS | **On** | **On** |

   Why East US: Vercel functions run in Washington DC (`iad1`) by default, and the database should sit next to the API. It also keeps API traffic out of the EEA, UK and Switzerland, where the Gemini free tier isn't offered.

3. Free organizations get two active projects, so these use the whole allowance. A project pauses after 7 days without activity; restore it from the dashboard.

## 4. Connect the repo to `cardwise-prod`

1. `cardwise-prod` → Project Settings → Integrations → GitHub Integration → **Authorize GitHub** → Authorize Supabase.
2. When GitHub asks where to install the Supabase app, choose the **Cardwise-ai** organization and **Only select repositories → cardwise**.
3. Back in Supabase, fill in:

   | Option | Value |
   |---|---|
   | Repository | `Cardwise-ai/cardwise` |
   | Working directory | `.` |
   | Production branch | `main` |
   | Deploy to production | **On** |
   | Automatic branching | Off (preview branches are paid) |

4. **Enable integration.** The next push to `main` applies `supabase/migrations/*` and creates the `raw-snapshots` bucket.
5. Check it: Database → Migrations lists `20261121120000_init`; Table Editor → schema `corpus` has the tables; Storage lists `raw-snapshots` as private.

**Rule from now on:** change either schema only through a migration file merged to `dev` (then released to `main`). If you edit tables in the dashboard, the migration history stops matching the repo and the next deploy fails.

## 5. Connect the repo to `cardwise-dev`

Same as step 4, in `cardwise-dev` → Project Settings → Integrations → GitHub Integration. The Supabase app is already installed on the repo, so GitHub won't ask again. Use the same options except:

| Option | Value |
|---|---|
| Production branch | `dev` |

The next push to `dev` applies any migration `cardwise-dev` hasn't seen and creates `raw-snapshots`. Check it the same way as step 4.

If the dev database ever needs a migration by hand (for example after a reset), run from the repo root in PowerShell:

```sh
pnpm exec supabase login                       # opens the browser once
pnpm exec supabase db push --remote=<dev-ref> --yes
```

Supabase CLI 3.x pushes to the local Docker database unless `--remote` is given. `<dev-ref>` is in the dev project's URL: `https://supabase.com/dashboard/project/<dev-ref>`.

## 6. Sign-in

Supabase Auth's email and password sign-in, invite-only, with no email sending. Supabase's built-in email delivers only to members of your Supabase org, at 2 emails an hour, and free SMTP providers need a domain you own. So the POC sends no email at all: you create each tester's account yourself and give them the password. GitHub or Google sign-in would also work, but each needs an OAuth app registered with that provider.

In both projects:

1. Authentication → Sign In / Providers:
   - **Allow new users to sign up: off.** Only accounts you create exist.
   - **Email** provider: on. **Confirm email: off**, so no confirmation email is sent.
   - All other providers: off.
2. Authentication → URL Configuration:

   | Field | Production | Development |
   |---|---|---|
   | Site URL | the `cardwise-web` production URL (step 7) | `http://localhost:3000` |
   | Redirect URLs | `<web production URL>/**` | `http://localhost:3000/**` and `https://cardwise-web-*-<vercel-scope>.vercel.app/**` (previews) |

3. Authentication → Users → **Add user → Create new user**: enter the email and a generated password, and tick **Auto Confirm User**. Do this for yourself in both projects and for each tester in production. Send passwords through a password manager share or Signal, not plain email. If someone forgets theirs, reset it on the same page.

Password reset and email change by the user need email, so they wait for SMTP (after the POC, with a domain).

## 7. Vercel: web project

1. vercel.com/new → **Import Git Repository** → Install the Vercel app on **Cardwise-ai**, **Only select repositories → cardwise** → Import `cardwise`.
2. Configure:

   | Setting | Value |
   |---|---|
   | Project name | `cardwise-web` |
   | Framework preset | Next.js |
   | Root directory | `apps/web` |
   | Build and install commands | defaults (Vercel detects pnpm from the lockfile) |

3. Deploy. The placeholder page should load at the production URL.
4. Project Settings:
   - Functions → Function region: **Washington, D.C. (iad1)**.
   - Deployment Protection → Vercel Authentication: **Standard Protection**, so previews need a Vercel login.
   - Environment Variables (add them now; the web app reads them from Line E on). The setup script sets the first two with `vercel env add --project cardwise-web --scope <scope> --force`:

   | Name | Production | Preview and Development |
   |---|---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<prod-ref>.supabase.co` | `https://<dev-ref>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | prod publishable key | dev publishable key |
   | `NEXT_PUBLIC_API_URL` | `cardwise-api` production URL (after step 8) | `cardwise-api` preview URL, or `http://127.0.0.1:8000` |
   | `NEXT_PUBLIC_LLM_TIER` | `free` (`paid` hides the free-tier notice) | `free` |

   The publishable key is under Supabase → Project Settings → API Keys (`sb_publishable_...`). It is public by design. The secret key (`sb_secret_...`, formerly `service_role`) is never used anywhere.

## 8. Vercel: API project

The API is deployed to Vercel for dev. Production is intentionally not configured or deployed until S2 passes.

Current dev setup:
- Vercel project `cardwise-api` is connected to `Cardwise-ai/cardwise`, with framework **FastAPI**, root directory `api`, source files outside the root enabled, and production branch `main`.
- The Preview deployment is available at `https://cardwise-api-git-dev-yhaliwaizman.vercel.app`; its `/healthz` returns `{"status":"ok"}` and unauthenticated `GET /v1/chats` returns 401.
- Preview uses the dev Supabase project and transaction pooler, dev model keys, and a CORS regex for web preview origins. `cardwise-web` Preview uses this API URL.
- Vercel Authentication stays enabled on the web project. It is disabled on the API project because browser-to-API requests cannot use the Vercel SSO flow; all `/v1` routes require a Supabase JWT, while `/healthz` is intentionally public.
- Both Supabase JWKS endpoints currently advertise ES256 signing keys.

What's in the repo:
- `api/index.py` re-exports `cardwise_api.main:app`; `[tool.vercel] entrypoint = "index:app"` in `api/pyproject.toml` points Vercel at it.
- `api/vercel.json` pins the region to `iad1`, lets the function run 300 s (a long answer stream) and leaves tests out of the bundle.

Steps:

1. Check the token signing keys on **both** Supabase projects: Project Settings → **JWT Keys**. The current key must be asymmetric (ECC P-256 or RSA). If it still says "Legacy JWT secret", click **Migrate JWT secret**, then **Rotate keys** so the new ECC key signs tokens. The API only accepts ES256/RS256 tokens checked against `<project URL>/auth/v1/.well-known/jwks.json`; it never sees a JWT secret.
2. The project is created and connected to the repository as described above.
3. Project Settings → Build and Deployment → Root Directory → **Include files outside the root directory: On**. The API imports `packages/core` and `packages/llm` from the uv workspace.
4. Do not enable Vercel Authentication for this API project: it blocks browser requests from the web app. Function region is set by `vercel.json`; API authorization is enforced with Supabase JWTs.
5. Environment variables, all **sensitive**:

   | Name | Production | Preview |
   |---|---|---|
   | `CARDWISE_DATABASE_URL` | prod **Transaction pooler** URL (port 6543) | dev Transaction pooler URL |
   | `CARDWISE_SUPABASE_URL` | `https://<prod-ref>.supabase.co` | `https://<dev-ref>.supabase.co` |
   | `CARDWISE_WEB_ORIGIN` | web production URL, e.g. `https://cardwise-web.vercel.app` (comma-separate several) | web preview branch URL(s), or leave unset and use the regex below |
   | `CARDWISE_WEB_ORIGIN_REGEX` | unset | `^https://cardwise-web-[a-z0-9-]+-<team-slug>\.vercel\.app$` |
   | `CARDWISE_GEMINI_API_KEY` | prod key | dev key |
   | `CARDWISE_OPENROUTER_API_KEY` | prod key | dev key |

   The pooler URL is under Supabase → **Connect** → Transaction pooler; put the database password into it. Use port **6543**: the API opens one connection per request and never prepares named statements, which is what the transaction pooler needs (ADR 0007). `VERCEL_ENV` tells the app it is deployed: it then refuses to start without `CARDWISE_DATABASE_URL` and an https `CARDWISE_SUPABASE_URL`, sends HSTS and hides `/openapi.json`. Optional tuning: `CARDWISE_LOG_LEVEL`, `CARDWISE_MESSAGES_PER_HOUR` (default 20), `CARDWISE_CONCURRENT_STREAMS` (default 1).
6. Deploy a Preview, then check `https://<api-url>/healthz` returns `{"status":"ok"}` and `GET /v1/chats` without a token returns 401 with the JSON error shape. The dev Preview currently passes both checks.
7. Set `NEXT_PUBLIC_API_URL` on `cardwise-web` Preview to the API Preview URL. The dev Preview currently uses `https://cardwise-api-git-dev-yhaliwaizman.vercel.app`; do not set the production web value until S2 passes.

If the build can't install the workspace packages, fall back to a pinned requirements file: `uv export --package cardwise-api --no-dev --frozen --no-hashes -o api/requirements.txt` plus copying `packages/*/src` into the bundle, and record what worked here.

## 9. Model providers

**Google AI Studio (Gemini, primary)**
1. aistudio.google.com/apikey → **Create API key** → in a new Google Cloud project named `cardwise`.
2. Do not enable billing on that project. A project with billing on is charged at paid rates.
3. Make one key per environment (`cardwise-prod`, `cardwise-dev`) so you can revoke one without the other.
4. The free tier may use prompts for training and human review. That's acceptable only because of ADR 0004: prompts contain chat text and public card data, nothing else.

**OpenRouter (fallback)**
1. openrouter.ai/settings/keys → **Create key**, one per environment, with credit limit **0**.
2. Don't buy credits. Free models then allow 20 requests a minute and 50 a day per account.
3. Settings → Privacy: allow providers that may train on prompts. Most `:free` models require it, and ADR 0004 covers it.

## 10. GitHub Actions secrets

CI needs none: it runs against a local Supabase in Docker with the fake model. The `ingest` workflow needs a GitHub **Environment** per Supabase project. `dev` and `prod` exist already (repo → Settings → Environments); `dev` only accepts runs from the `dev` branch and `prod` only from `main`. `scripts/sync_env.py` (below) fills them in for you. By hand, add these secrets to **each** environment, with that project's values:

| Secret | Workflow | Where to get it |
|---|---|---|
| `CARDWISE_DATABASE_URL` | ingest, chat backups | Supabase → **Connect** → Connection string → **Session pooler** (port 5432), with the database password filled in. It looks like `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`. GitHub runners can't reach the IPv6-only direct connection, and the transaction pooler breaks the session lock ingest takes. |
| `CARDWISE_STORAGE_S3_ENDPOINT` | ingest | Project Settings → Storage → **S3 Connection** → Endpoint (`https://<ref>.storage.supabase.co/storage/v1/s3`) |
| `CARDWISE_STORAGE_S3_REGION` | ingest | same section → Region |
| `CARDWISE_STORAGE_S3_ACCESS_KEY_ID` / `CARDWISE_STORAGE_S3_SECRET_ACCESS_KEY` | ingest | same page → **S3 Access Keys** → New access key. The secret is shown once. These keys can read and write every bucket in the project but nothing else. |
| `CARDWISE_BACKUP_AGE_RECIPIENT` | chat backups (later) | the public key from `age-keygen -o cardwise-backup.key`. Keep `cardwise-backup.key` offline, never in GitHub. |
| `CARDWISE_GEMINI_API_KEY` / `CARDWISE_OPENROUTER_API_KEY` | live evals (later) | dev keys |

The S3 secrets are optional: without them ingest still loads the database and logs that the raw files were not archived.

`ingest` runs every Monday on `dev` into the dev project; if that succeeds it starts a prod run on `main`. Run it by hand from Actions → ingest → **Run workflow**: pick branch `dev` with environment `dev`, or branch `main` with environment `prod` (any other pairing is refused by the environment). A run on unchanged files does nothing. If the card count moves more than 5%, the run fails and the live corpus stays; check the data, then rerun with **allow count drift**.

Dependabot PRs can't read secrets, so jobs that use them run only on `dev`, `main` or by hand.

### Sync script

`scripts/sync_env.py` sets the GitHub environment secrets above and the two `NEXT_PUBLIC_SUPABASE_*` Vercel variables (step 7) for both projects. It reads the refs and Vercel scope from `.env.hosted`, looks up the pooler host, region and publishable key through the Supabase Management API, and asks only for what Supabase never shows again: the database password and the S3 access key pair. It tests each value against the live service before writing it, writes nothing to disk, and is safe to rerun. Run it from the repo root in PowerShell after `pnpm exec supabase login`, `gh auth login` and `npx vercel login`:

```sh
uv run python scripts/sync_env.py --dry-run     # check only
uv run python scripts/sync_env.py               # both projects
uv run python scripts/sync_env.py --env dev     # one project
```

An empty answer skips that group. Rotating the database password or an S3 key means rerunning it.

## 11. Local `.env`

Copy `.env.example` to `.env` (API) and `apps/web/.env.local` (web). For local work, point them at the local stack: `pnpm exec supabase start` prints the URLs and the local publishable key. Model keys stay empty to use the fake model, or hold the dev keys.

The API only accepts asymmetric (ES256/RS256) tokens. If the local stack still signs with the legacy HS256 secret, generate a key with `pnpm exec supabase gen signing-key --algorithm ES256` (it writes `supabase/signing_keys.json`; never commit it), set `signing_keys_path = "./signing_keys.json"` under `[auth]` in `supabase/config.toml` locally, and restart the stack. Run the API with `uv run --with uvicorn uvicorn cardwise_api.main:app --reload --port 8000`.

## Values to send back

None of these are secret. Paste them in chat or into an issue, and the next tasks use them:

- `<prod-ref>` and `<dev-ref>`
- the `cardwise-web` production URL and Vercel scope (team slug)
- confirmation that the integration applied `20261121120000_init` to prod

The setup script `scripts/setup-hosted.sh` walks through steps 1 to 9. It records the values in `.env.hosted` (git-ignored), writes the dev model keys to `.env` for local runs, and sets the `cardwise-web` environment variables in Vercel through the Vercel CLI (it asks you to log in once). If the CLI step fails, it prints the values to paste on the Environment Variables page instead. Run it from Git Bash: `bash scripts/setup-hosted.sh`.
