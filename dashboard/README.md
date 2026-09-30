# ML Platform Ops Dashboard

Module 8. A read-only status view for the 3 SageMaker-routed proxy services, with a
one-click "run test prediction" button per service. Calls each service directly from
the browser (no backend in between) — see the main project write-up for why.

## Setup

```bash
npm install
npm run dev
```

Opens at http://localhost:5173.

### 1. CORS on the proxy services

Each of the 3 services needs `CORSMiddleware` allowing this dashboard's origin — see
the project's Module 8 notes for the exact patch to `services/*/main.py`. Without it,
the browser will block every request from this dashboard with a CORS error (visible in
the browser console, and the dashboard's status dots will show "unreachable").

### 2. Port-forward all 3 services

This dashboard calls `localhost:8001/8002/8003` directly, so all 3 services need to be
reachable there — same as manual testing throughout this project:

```bash
kubectl port-forward -n ml-platform svc/endpoint1-flex 8001:80 &
kubectl port-forward -n ml-platform svc/endpoint2-xenium 8002:80 &
kubectl port-forward -n ml-platform svc/endpoint3-spatial 8003:80 &
```

### 3. Sample payloads for the "Run test prediction" button

The button fetches a pre-canned payload from `public/test-payloads/<service-id>.json`
and POSTs it to that service's `/predict`. These files are **not** included as-is,
since endpoint1/2's `test_payload.json` uses a top-level `"example_cells"` key that
needs wrapping into `{"cells": [...]}` before it matches what `/predict` expects
(endpoint3's is already correctly shaped). Generate all 3 from the project root:

```bash
mkdir -p dashboard/public/test-payloads

python3 -c "
import json
d = json.load(open('services/endpoint1-flex/model_artifacts/test_payload.json'))
json.dump({'cells': d['example_cells']}, open('dashboard/public/test-payloads/endpoint1-flex.json', 'w'))
"

python3 -c "
import json
d = json.load(open('services/endpoint2-xenium/model_artifacts/test_payload.json'))
json.dump({'cells': d['example_cells']}, open('dashboard/public/test-payloads/endpoint2-xenium.json', 'w'))
"

cp services/endpoint3-spatial/model_artifacts/test_payload.json \
   dashboard/public/test-payloads/endpoint3-spatial.json
```

(These commands are the exact same payload-wrapping logic used throughout this
project's manual end-to-end testing — nothing new here, just packaged for the button.)

Files under `public/test-payloads/` are gitignored by default reasoning that test
fixtures shouldn't live twice in the repo — if you'd rather commit them for a
one-command demo setup, remove that line from `.gitignore` and `git add` them.

## What "Run test prediction" actually does

Not a general data-entry form — SageMaker expects a fixed 4512-value gene expression
vector per cell, which isn't something to type into a UI. The button sends the same
known-good sample payload used throughout this project's manual validation and
displays the real response from the live SageMaker endpoint (through the Kubernetes
proxy), so a demo can show the whole pipeline working end-to-end with one click instead
of a terminal.
