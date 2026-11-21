# 0004: What data may go to free-tier model providers

Status: accepted
Date: 2026-11-21

## Context
Free tiers of Gemini and OpenRouter models may train on prompts and allow human review. The Gemini free tier is not available for users in the EEA, UK or Switzerland. Model quality and commercial use are deferred until after the POC.

## Decision
- While on free tiers, prompts contain only the user's chat text and public card data. No email, user ID or other account data is ever sent to a provider.
- The UI tells users that messages go to a third-party model that may use them for training.
- Any move to commercial use or to EEA/UK users requires paid tiers first.

## Consequences
- The POC is a private test, not a product launch.
- Logging must never include message bodies (they are already excluded by design).
