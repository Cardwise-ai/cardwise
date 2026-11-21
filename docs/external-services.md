# External services setup

Everything Cardwise needs outside this repo, in the order to set it up. Every service here is on a free plan and none asks for a payment card.

Secrets go straight from a dashboard into Vercel, GitHub or your local `.env`. They never go in chat, in commits or in this file.

## How the pieces connect

| Service | Plan | Connected to the repo by | Deploys |
|---|---|---|---|
| Supabase `cardwise-prod` | Free | Supabase GitHub integration | Migrations and storage buckets on every push to `main` |
| Supabase `cardwise-dev` | Free | Supabase CLI from your machine | Migrations when you run `supabase db push` |
| Vercel `cardwise-web` | Hobby | Vercel GitHub app | Web app: production from `main`, a preview for every PR |
| Vercel `cardwise-api` | Hobby | Vercel GitHub app | API, once the endpoints exist (Line C) |
| Google AI Studio | Free tier | API key in Vercel | n/a |
| OpenRouter | Free models | API key in Vercel | n/a |
| GitHub Actions | Free | This repo | CI now; ingest, backups and live evals later |

**Why the Supabase GitHub integration instead of a deploy workflow:** on every plan, the integration applies new migrations and creates the storage buckets declared in `supabase/config.toml` when `main` changes. No access token, project ID or database password has to live in GitHub. Preview branches (a database per PR) are a paid add-on, so we don't use them. CI already tests every migration against a fresh local Supabase.

The integration does not deploy Auth or API settings by default. Those are set once in the dashboard (steps 5 and 6).

## 1. Accounts and identity

1. Make sure `yhaliwa1@gmail.com` (the git commit email) is a verified email on your GitHub account: github.com → Settings → Emails. Vercel Hobby deploys a private repo only for commits by the account owner, and it matches by this email.
2. Create these accounts, all with "Continue with GitHub":
   - supabase.com
   - vercel.com (choose **Hobby**, personal use)
   - openrouter.ai
3. Use a Google account for Google AI Studio (step 9). A separate Google account for Cardwise keeps it apart from your personal data.

## 2. Repo protection

GitHub Free organizations can't protect branches in private repos. Until the repo is public or the org is on Team, branch rules are a habit, not enforced:
- merge to `main` only through PRs with green CI;
- Settings → General → Pull Requests: allow squash merge only, and turn on "Automatically delete head branches".

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

**Rule from now on:** change the production schema only through a migration file merged to `main`. If you edit tables in the dashboard, the migration history stops matching the repo and the next deploy fails.

## 5. Bring `cardwise-dev` up to date

Run these from the repo root on your machine:

```sh
pnpm exec supabase login                       # opens the browser once
pnpm exec supabase link --project-ref <dev-ref> # asks for the dev database password
pnpm exec supabase db push
```

`<dev-ref>` is in the dev project's URL: `https://supabase.com/dashboard/project/<dev-ref>`.

Then create the bucket by hand: Storage → New bucket → `raw-snapshots`, private, 50 MB file limit.

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
   - Environment Variables (add them now; the web app reads them from Line E on):

   | Name | Production | Preview and Development |
   |---|---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<prod-ref>.supabase.co` | `https://<dev-ref>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | prod publishable key | dev publishable key |
   | `NEXT_PUBLIC_API_URL` | `cardwise-api` production URL (after step 8) | `cardwise-api` preview URL, or `http://127.0.0.1:8000` |

   The publishable key is under Supabase → Project Settings → API Keys (`sb_publishable_...`). It is public by design. The secret key (`sb_secret_...`, formerly `service_role`) is never used anywhere.

## 8. Vercel: API project (when Line C has endpoints)

Not needed yet, because the API is still stubs. When it's time:

1. vercel.com/new → import `cardwise` again → project name `cardwise-api`, framework **FastAPI**, root directory `api`.
2. Project Settings → Build and Deployment → Root Directory → **Include files outside the root directory: On**. The API imports `packages/core` and `packages/llm`. Packaging the uv workspace on Vercel is untested, so the first API deploy task proves it.
3. Function region **iad1**; Deployment Protection as above.
4. Environment variables, all **sensitive**:

   | Name | Production | Preview |
   |---|---|---|
   | `CARDWISE_DATABASE_URL` | prod **Transaction pooler** URL (port 6543) | dev Transaction pooler URL |
   | `CARDWISE_SUPABASE_URL` | `https://<prod-ref>.supabase.co` | `https://<dev-ref>.supabase.co` |
   | `CARDWISE_WEB_ORIGIN` | web production URL | web preview URL pattern |
   | `CARDWISE_GEMINI_API_KEY` | prod key | dev key |
   | `CARDWISE_OPENROUTER_API_KEY` | prod key | dev key |

   The pooler URL is under Supabase → **Connect** → Transaction pooler; put the database password into it. The API verifies tokens with the project's public keys at `<project URL>/auth/v1/.well-known/jwks.json`, so no JWT secret is needed.

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

**None are needed now.** CI runs against a local Supabase in Docker with the fake model, and Supabase and Vercel deploy through their own GitHub apps.

When these workflows are built, create a GitHub **Environment** named `prod` (repo → Settings → Environments). Restrict it to the `main` branch, then add:

| Secret | Workflow | Value |
|---|---|---|
| `CARDWISE_DATABASE_URL` | ingest, chat backups | prod **Session pooler** URL (port 5432). GitHub runners can't reach the IPv6-only direct connection, and the transaction pooler breaks long loads. |
| `CARDWISE_STORAGE_S3_ENDPOINT` | ingest | Supabase → Project Settings → Storage → S3 connection endpoint |
| `CARDWISE_STORAGE_S3_REGION` | ingest | same page |
| `CARDWISE_STORAGE_S3_ACCESS_KEY_ID` / `CARDWISE_STORAGE_S3_SECRET_ACCESS_KEY` | ingest | same page → **New access key**. These keys reach Storage only. |
| `CARDWISE_BACKUP_AGE_RECIPIENT` | chat backups | the public key from `age-keygen -o cardwise-backup.key`. Keep `cardwise-backup.key` offline, never in GitHub. |
| `CARDWISE_GEMINI_API_KEY` / `CARDWISE_OPENROUTER_API_KEY` | live evals | dev keys |

Dependabot PRs can't read secrets, so jobs that use them run only on `main` or by hand.

## 11. Local `.env`

Copy `.env.example` to `.env` (API) and `apps/web/.env.local` (web). For local work, point them at the local stack: `pnpm exec supabase start` prints the URLs and the local publishable key. Model keys stay empty to use the fake model, or hold the dev keys.

## Values to send back

None of these are secret. Paste them in chat or into an issue, and the next tasks use them:

- `<prod-ref>` and `<dev-ref>`
- the `cardwise-web` production URL and Vercel scope (team slug)
- confirmation that the integration applied `20261121120000_init` to prod

The setup script `scripts/setup-hosted.sh` walks through steps 1 to 9 and records the values in `.env.hosted` (git-ignored). Run it from Git Bash: `bash scripts/setup-hosted.sh`.
