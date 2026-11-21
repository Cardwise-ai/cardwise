# 0002: FastAPI deployed as its own Vercel project

Status: accepted
Date: 2026-11-21

## Context
The agent loop, retrieval and Pydantic models are Python. Vercel runs FastAPI as a Python function on the Hobby plan at no cost. The web app is Next.js.

## Decision
- The API is a FastAPI app in `api/`, deployed as a separate Vercel project rooted at `api/`.
- The browser calls the API directly with the Supabase access token as a bearer token. The API verifies the JWT and is the only writer to the database.
- The OpenAPI document is generated from the app (`python -m cardwise_api.export_schemas`) and the web client is generated from it.

## Consequences
- Two Vercel projects and two sets of environment variables.
- CORS must allow only the web origin.
- Vercel Hobby deploys private repos only for commits by the Hobby account owner. Fine while solo; collaborators need the repo public or a Pro plan.
