# VocalGrid web deployment

Vercel hosts the marketing pages and account UI. Supabase provides Auth and account-owned
meeting preferences. Modal remains a separate translation service; Vercel does not execute
speech models. Website login does not currently secure the existing Modal WebSocket.

## Build

`npm ci && npm run build` produces `dist/` using a public-site-only allowlist boundary.
Set Vercel root directory to this repository root and use the committed vercel.json.

Environment variables:
- `PUBLIC_SUPABASE_URL`: dedicated VocalGrid project URL (HTTPS).
- `PUBLIC_SUPABASE_PUBLISHABLE_KEY`: public publishable key or legacy anon key. Never service-role/secret keys.
- `PUBLIC_SITE_URL`: final production origin, once domain is selected. Leave unset on previews.

Supabase:
1. Create/select the dedicated project; do not apply this schema to another product's database.
2. Apply `supabase/migrations/202609290001_meeting_profiles.sql` through the migration workflow.
3. Configure Auth Site URL and exact allowed `/account` redirect URLs for deployment and localhost.
4. Enable email authentication and configure production SMTP before broad signups. Provider default mail limits may restrict delivery.
5. Test sign-in, sign-out, save/read/delete and cross-user denial using two test accounts. RLS is mandatory.

The auth SDK uses PKCE and browser session storage via its supported localStorage mechanism.
Each profile belongs to auth.uid(); anonymous access is denied. User deletion cascades profile
records but auth-user deletion requires a server-side administrative workflow (not exposed in browser).
Audio, transcripts and cloned voices are not stored in this schema. Do not use browser-supplied
usage amounts for billing.

Before requiring login for the speech service, validate Supabase tokens on the Modal server
and bind usage to verified user IDs. A frontend-only gate would not secure that API.
Existing Modal resource names and storage keys remain lingosync to avoid breaking deployed services;
customer-facing website/app labels, film and metadata are VocalGrid.

Checks: `npm test`, `node tests/site/check-build.mjs`.
Policy drafts remain drafts pending operator/contact/retention decisions. No paid billing,
recording storage or public domain purchase is implemented by this change.
