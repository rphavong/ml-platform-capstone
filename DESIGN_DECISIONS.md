# Design Decisions

Non-obvious choices worth knowing before Q&A — what they are, and why, in case they
come up.

- **IMDSv2 hop limit.** Pods get AWS credentials from the node's IAM role via the
  instance metadata service, which defaults to a hop limit of 1 — too low for a
  process running inside a pod's own network namespace (one extra hop away from the
  host). Fixed via a `aws_launch_template` with `http_put_response_hop_limit = 2`,
  wired into the node group (`terraform/eks.tf`). This is a direct consequence of not
  using IRSA (see next point) — with true IRSA, pods get credentials through a webhook
  instead of IMDS, and this wouldn't be needed at all.
- **Node-role credentials instead of IRSA.** The textbook-correct pattern for scoping
  AWS permissions to exactly one Kubernetes ServiceAccount is IRSA, which needs
  `iam:CreateOpenIDConnectProvider` — denied on this class AWS account (confirmed by a
  real `AccessDenied`). The `sagemaker:InvokeEndpoint` permission is attached to the
  *node's* IAM role instead (`terraform/eks-iam.tf`), a real, named trade-off: every
  pod on a node technically shares it, though still scoped to exactly these 3 SageMaker
  endpoints, not a blanket grant.
- **Secret-backed credential fallback.** Because node-role credentials mean no
  `Secret` object exists for AWS credentials by default, and the assessment rubric
  explicitly expects one, `pod-fallback-iam.tf` creates a second, independently-scoped
  IAM user (same `sagemaker:InvokeEndpoint`-only permission) whose keys live in a K8s
  `Secret` and are used **only** if the primary node-role path's credentials are
  unavailable (`services/*/main.py`'s `_invoke_with_fallback`). Deliberately named
  `AWS_BACKUP_*`, not `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, so they never
  silently override boto3's default credential chain.
- **GitHub Actions auth.** Same OIDC-provider permission wall as above (GitHub's
  recommended OIDC federation needs the identical denied permission), so CI uses a
  long-lived IAM access key stored as encrypted GitHub secrets — scoped to ECR push
  plus a namespace-limited EKS Access Entry, not an admin key.
- **Namespace-per-team mapping.** This is a single-author capstone, not a multi-team
  org, so "team" is mapped to *which trained model a service depends on* rather than a
  business unit: `single-cell-genomics` (endpoint1+2, sharing one model) and
  `spatial-analysis` (endpoint3, a separately-trained model with its own, larger
  resource footprint).
- **No `curl` in the proxy images.** `services/*/Dockerfile` builds a minimal
  `python:3.11-slim` image with no `curl` installed — its own `HEALTHCHECK` uses
  Python's `urllib` instead. This bit debugging once already (a `kubectl exec ... curl`
  command silently failed with "executable file not found"), so `cd.yml`'s live
  `/health` verification step deliberately uses the same `urllib` approach rather than
  repeating that mistake.
- **`package_and_deploy.py` is self-healing.** SageMaker's `create_model` /
  `create_endpoint_config` / `create_endpoint` calls are not idempotent — an earlier
  teardown that only deleted the endpoint (for cost savings) left the model and
  endpoint-config objects behind, causing `ValidationException: Cannot create already
  existing model` on the next deploy. `deploy()` now deletes any leftover objects
  (ignoring "not found" errors) before recreating, so reruns never collide again,
  whatever state the last teardown left things in.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the credential paths and routing fit
together at runtime, and [REPOSITORY_LAYOUT.md](REPOSITORY_LAYOUT.md) for where each
piece referenced above actually lives.
