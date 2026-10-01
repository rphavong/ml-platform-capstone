#!/usr/bin/env bash
# Run AFTER make_flex_test_payload.py. Propagates the new Flex-derived
# test_payload.json to the service's own copy and regenerates the dashboard's
# "Run test prediction" sample (per dashboard/README.md's documented wrapping step).
# No heavy deps needed - just the stdlib.
set -euo pipefail

cp model_artifacts/endpoint1_flex/test_payload.json \
   ../services/endpoint1-flex/model_artifacts/test_payload.json
echo "Synced -> services/endpoint1-flex/model_artifacts/test_payload.json"

mkdir -p ../dashboard/public/test-payloads

python3 -c "
import json
d = json.load(open('../services/endpoint1-flex/model_artifacts/test_payload.json'))
json.dump({'cells': d['example_cells']}, open('../dashboard/public/test-payloads/endpoint1-flex.json', 'w'))
"
echo "Synced -> dashboard/public/test-payloads/endpoint1-flex.json"

# endpoint2's payload is untouched (it was already genuine Xenium data) - just
# regenerate its dashboard copy too in case it's stale/missing.
python3 -c "
import json
d = json.load(open('../services/endpoint2-xenium/model_artifacts/test_payload.json'))
json.dump({'cells': d['example_cells']}, open('../dashboard/public/test-payloads/endpoint2-xenium.json', 'w'))
"
echo "Synced -> dashboard/public/test-payloads/endpoint2-xenium.json"

echo "Done. endpoint1's dashboard button now sends real held-out Flex cells;"
echo "endpoint2's still sends real Xenium cells. They will now differ."
