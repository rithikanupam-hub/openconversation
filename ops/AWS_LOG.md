# AWS change log (OpenConversation)

Account `…2986` (shared with the scrapbook project), profile `scrapbook-eu`, region `eu-central-1` (Frankfurt).
CLI helper: `sh ~/scrapbook-web/ops/aws-cli.sh <args> --profile scrapbook-eu --region eu-central-1`.
Every resource we create is tagged `Project=openconversation` and listed here. Anything that costs money is
approved by the owner first.

| Date | Change | Cost | Status |
|---|---|---|---|
| 2026-09-26 | Read-only check: GPU quotas 0 (on-demand and spot G/VT), no instances running; g6.xlarge (L4), g6e.xlarge, g5.xlarge offered in eu-central-1 | free | done |
| 2026-09-26 | Service quota request: Running On-Demand G and VT instances → 8 vCPU (id 961bd9b9…) | free | PENDING |
| 2026-09-26 | Service quota request: All G and VT Spot Instance Requests → 8 vCPU (id d7355647…) | free | PENDING |
