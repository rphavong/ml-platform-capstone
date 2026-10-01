# Repository Layout

See [ARCHITECTURE.md](ARCHITECTURE.md) for how these pieces connect at runtime.

## Root

| Path | What it is |
|---|---|
| `.github/workflows/` | CI/CD pipeline — see table below |
| `terraform/` | All AWS infrastructure as code — see table below |
| `k8s/` | Kubernetes manifests applied to EKS — see table below |
| `services/` | The 3 FastAPI proxy services that run in Kubernetes — see table below |
| `sagemaker-packaging/` | The 3 SageMaker BYOC (bring-your-own-container) packages that run *inside* SageMaker — see table below |
| `dashboard/` | React ops dashboard — see table below |
| `ec2-pipeline-pulled/` | The biology pipeline that produced every model/data artifact this platform serves — see table below |
| `aws-setup/` | Superseded by `terraform/iam.tf` — kept only as a record of the manual IAM setup before Terraform took over (gitignored) |
| `_archive/` | Pre-refactor versions of the 3 services, back when they loaded and ran the model in-process instead of proxying to SageMaker (see `services/*/main.py`'s own docstring for what changed and why) |
| `.gitignore`, `.dockerignore` | Exclude venvs, build artifacts, large biology data files (`.h5ad`/`.h5`/`.parquet`), and Terraform state |
| `ARCHITECTURE.drawio` | The same architecture diagram as [ARCHITECTURE.md](ARCHITECTURE.md), as an editable draw.io file |

## `.github/workflows/`

| File | Purpose |
|---|---|
| `test.yml` | Reusable workflow — matrix over all 3 services, runs `pytest` for each |
| `ci.yml` | Runs `test.yml` on every pull request into `main` |
| `cd.yml` | Runs on every push to `main`: `test` → `build-and-push` (Docker build, push `:k8s-proxy` and `:<sha>` tags to each service's ECR repo) → `deploy` (`kubectl set image`, `rollout status`, then a live `/health` check inside the new pod via `kubectl exec` — verification steps required by the rubric) |

## `terraform/`

| File | Purpose |
|---|---|
| `provider.tf` | AWS provider + `aws_caller_identity` data source (used everywhere instead of hardcoding the account ID) |
| `variables.tf` | Region, project name prefix, EKS version, node sizing — all overridable, no hardcoded values baked into resources |
| `versions.tf` | Pins Terraform + AWS provider versions, so `init` months from now can't silently pull a different provider and change behavior |
| `vpc.tf` | Uses the account's default VPC/subnets (a dedicated VPC wasn't worth a NAT gateway's cost for a class demo cluster) |
| `eks.tf` | The EKS cluster + node group, a launch template raising the node's IMDSv2 hop limit to 2 (pods need this to reach the node IAM role's credentials), and the `access_config` enabling EKS Access Entries alongside the original aws-auth ConfigMap |
| `eks-iam.tf` | Two IAM roles: one for the EKS control plane, one for worker nodes (which also carries the `sagemaker:InvokeEndpoint` permission the proxy pods use via the node-role-as-credential-source pattern) |
| `iam.tf` | The SageMaker execution role + its S3/CloudWatch/ECR-pull inline policies |
| `ecr.tf` | The 3 ECR repositories (one per endpoint image), defined once via `for_each` over a `local.endpoint_names` list |
| `s3.tf` | The S3 bucket holding packaged `model.tar.gz` artifacts for SageMaker |
| `github-actions-iam.tf` | A dedicated IAM user + access key for CI, scoped to ECR push on only these 3 repos |
| `github-actions-eks-access.tf` | An EKS Access Entry + namespace-scoped `AmazonEKSEditPolicy` association for that same CI user, so `cd.yml`'s deploy job can `kubectl` without being cluster-admin, plus the `eks:DescribeCluster` permission needed just to fetch kubeconfig |
| `pod-fallback-iam.tf` | A third, separate IAM user scoped to only `sagemaker:InvokeEndpoint` on these 3 endpoints — backs the K8s `Secret`-based credential fallback path |
| `vpc-endpoint-access.tf` | One standalone security-group rule (not an owned SG) opening 443 from the EKS cluster's SG to the pre-existing shared SageMaker PrivateLink VPC endpoint — the real fix for a `NoCredentialsError`/timeout chain hit during live testing |
| `outputs.tf` | Role ARNs, ECR URLs, cluster name/endpoint, and the ready-to-run `aws eks update-kubeconfig` command |
| `.gitignore` | Excludes `.terraform/`, all `*.tfstate*` files (plaintext-sensitive), `*.tfvars`, and saved plan files |

## `k8s/`

| File | Purpose |
|---|---|
| `00-namespaces.yaml` | The two team namespaces: `single-cell-genomics` (endpoint1+2) and `spatial-analysis` (endpoint3) |
| `01-configmap-single-cell-genomics.yaml` / `01-configmap-spatial-analysis.yaml` | Non-sensitive config (AWS region, per-endpoint SageMaker endpoint names) — the "explicit routing" made visible in the manifest itself |
| `02-endpoint1.yaml` / `03-endpoint2.yaml` / `04-endpoint3.yaml` | Deployment + Service per proxy: startup/liveness/readiness probes, resource requests/limits, ConfigMap + Secret-backed env vars |
| `05-quota-single-cell-genomics.yaml` / `06-quota-spatial-analysis.yaml` | `ResourceQuota` (namespace-wide ceiling) + `LimitRange` (per-container defaults/bounds) for each namespace |
| `create-fallback-secret.sh` | Creates the `sagemaker-invoke-fallback` Secret in both namespaces from Terraform outputs — imperative, so no real key material is ever committed to git |

## `services/` (the Kubernetes-side FastAPI proxies — Module 4b)

Each of `endpoint1-flex/`, `endpoint2-xenium/`, `endpoint3-spatial/` contains:

| File | Purpose |
|---|---|
| `main.py` | The thin FastAPI proxy: `/health`, `/ready`, `/info`, `/predict`. Validates input shape locally, then calls the real model via `sagemaker-runtime.invoke_endpoint()` — primary credentials from the node IAM role, falling back to the `Secret`-backed scoped IAM user only if that path is unavailable. Translates SageMaker failure modes into clear HTTP errors (504 timeout, 502 unreachable/error, 400 bad input) |
| `Dockerfile` | Single-stage `python:3.11-slim` image, non-root user, `HEALTHCHECK` using `urllib` (no `curl` in the image — see [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)) |
| `requirements.txt` / `requirements-dev.txt` | Runtime deps (fastapi, boto3, numpy, pydantic) vs. test-only deps (pytest, httpx) |
| `test_main.py` | Unit tests — mocks `main.runtime.invoke_endpoint` to test the proxy's own logic (validation, error translation) without a real SageMaker call |
| `model_artifacts/` | `schema.json` (feature count, class list — used for local request validation) and `test_payload.json` (real sample cells, used by CI tests and the dashboard's "Run test prediction" button) |

## `sagemaker-packaging/` (the SageMaker-side BYOC containers — Module 4a)

Each of `endpoint1-byoc/`, `endpoint2-byoc/`, `endpoint3-byoc/` contains:

| File | Purpose |
|---|---|
| `package_and_deploy.py` | Builds `model.tar.gz`, uploads to S3, and deploys the SageMaker endpoint. Self-heals on rerun — cleans up any leftover model/endpoint-config/endpoint from a prior partial teardown before recreating, so redeploying before a demo never collides with `ValidationException: Cannot create already existing model`. Also supports `--teardown-only` for a fast, deliberate cost-saving teardown between sessions (keeps the S3 artifact and ECR image, only deletes the live SageMaker objects) |
| `sagemaker_serve.py` | The actual model-serving FastAPI app that runs **inside** the SageMaker container — answers SageMaker's required `/ping` and `/invocations` contract. Endpoint3's version additionally reconstructs the spatial-neighbor feature graph at inference time |
| `Dockerfile` | Multi-stage build (`gcc`/`g++` only in the build stage), `--platform linux/amd64` for SageMaker's x86_64 instances, `ENTRYPOINT ["serve"]` matching SageMaker's `docker run <image> serve` contract |
| `serve` | The shell script SageMaker actually executes — launches `uvicorn sagemaker_serve:app` on port 8080 |
| `requirements.txt` | Includes `xgboost`, `scikit-learn`, `joblib` — the real model-serving dependencies (absent from `services/*/requirements.txt`, since those are thin proxies with no model in-process) |

## `dashboard/` (Module 8 — React ops dashboard)

| File | Purpose |
|---|---|
| `src/api.ts` | Service registry (3 base URLs) + typed fetch helpers for `/health`, `/ready`, and `/predict`, each with a hard timeout via `AbortController` |
| `src/components/ServiceCard.tsx` | One card per service: polls health/readiness every 10s, shows a green/red status dot, and a "Run test prediction" button (disabled unless the service is healthy) that posts a real sample payload and renders the live SageMaker response |
| `src/components/ModelEvaluation.tsx` | Held-out classification accuracy for both models plus the gene-only-vs-spatial hard-case comparison - reads `public/model-eval.json`, produced offline by `ec2-pipeline-pulled/export_model_eval.py` |
| `src/components/CellMaps.tsx` | Container for the two cell-level scatter plots (Flex UMAP, Xenium physical tissue coordinates) - reads `public/flex-umap.json` and `public/xenium-spatial.json`, produced offline by `ec2-pipeline-pulled/export_embeddings.py` |
| `src/components/charts/EvidenceCharts.tsx` | Confidence histogram, agreement bar chart, and diverging class-shift chart used inside `ModelEvaluation.tsx` - hand-built inline SVG, no charting library dependency |
| `src/components/charts/ScatterPlot.tsx` | Canvas-rendered scatter plot with a clickable legend (hide/show a class), a malignancy-vs-cell-type color toggle, and a true/predicted (or gene-only/spatial) label toggle - shared by both panels in `CellMaps.tsx` |
| `src/App.tsx`, `src/main.tsx`, `src/vite-env.d.ts` | Standard React/Vite app scaffold |
| `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html` | Build/dev tooling config (React 18, Vite 6, TypeScript 5.7, dev server on port 5173) |
| `public/model-eval.json`, `public/flex-umap.json`, `public/xenium-spatial.json` | Pre-computed evidence files committed to git (unlike the gitignored `public/test-payloads/`) - regenerate with the two `export_*.py` scripts in `ec2-pipeline-pulled/` after retraining or re-deriving data |
| `README.md` | Setup steps: the CORS patch each proxy needs, port-forwarding all 3 services locally, and generating the 3 sample test payloads from `model_artifacts/test_payload.json` |

## `ec2-pipeline-pulled/` (the biology — not deployed, but produced everything that is)

| File | Purpose |
|---|---|
| `flex_module0.py` | Loads the raw Flex `.h5` matrix, runs initial QC |
| `annotate_clusters.py` | Leiden clustering → manual cluster-to-cell-type annotation |
| `marker_genes.py` | Differential expression per cluster (`sc.tl.rank_genes_groups`) to sanity-check the annotations |
| `add_gene_positions.py` | Maps genes to chromosomal coordinates (via GENCODE GTF) — required before CNV inference can work |
| `cnv_inference.py` | Infers copy-number variation per cell (`infercnvpy`) — the actual malignancy signal, not just cell-type labels |
| `inspect_cnv.py` | Ad-hoc inspection of CNV inference output |
| `confirm_malignant.py` | Validates CNV-based malignancy calls against known clinical marker genes (CDKN2A/p16, MKI67, TOP2A) |
| `finalize_labels.py` | Merges cell-type + CNV-based malignancy calls into the final training label used by `train_classifier.py` |
| `load_xenium.py` | Loads the raw Xenium expression matrix |
| `qc_xenium.py` | Xenium-appropriate QC thresholds (targeted panel ⇒ much lower per-cell counts than Flex is normal) |
| `inspect_panel.py` / `inspect_panel2.py` | Ad-hoc inspection of the raw Xenium gene-panel JSON |
| `extract_gene_panel.py` | Extracts the real gene list (filtering out negative-control/blank probes) from the panel JSON |
| `apply_classifier.py` | Applies the trained Flex-based classifier to Xenium cells (the actual "reference model" step) |
| `train_classifier.py` | Trains the shared endpoint1/endpoint2 classifier on Flex data, restricted to genes shared with the Xenium panel |
| `build_schema.py` | Writes each endpoint's `schema.json` (feature count, class list) from its trained model's artifacts |
| `make_test_payloads.py` | Builds the real sample test payloads used by CI, local testing, and the dashboard |
| `select_region.py` | Crops a real spatial region around confirmed malignant tissue, for spatial feature engineering |
| `spatial_features.py` | Engineers the 10-nearest-neighbor class-composition features and trains endpoint3's separate model |
| `validate_hard_cases.py` | Flags the cells the gene-expression-only model was least confident about - superseded by `evaluate_gene_only_vs_spatial.py` below, which finishes the comparison this only set up |
| `plot_predictions.py` | Renders a static spatial map of predicted labels (`malignant_spatial_map.png`) - superseded for interactive use by the dashboard's `xenium-spatial.json` panel, kept as the original one-off artifact |
| `make_flex_test_payload.py` | Builds a genuine Flex-derived test payload for endpoint1 (5 cells from the real held-out 20% split `train_classifier.py` evaluated against) - fixes endpoint1 and endpoint2 having shared a copy-pasted Xenium payload |
| `sync_endpoint1_payload.sh` | Propagates that new payload to `services/endpoint1-flex/model_artifacts/` and regenerates the dashboard's wrapped copy in `dashboard/public/test-payloads/` |
| `evaluate_endpoint1.py` | Reproduces `train_classifier.py`'s held-out `classification_report` **without retraining** - reloads the saved model/encoder/feature-genes and re-predicts on the identical split. Covers endpoint1 and endpoint2 (same model). Writes `endpoint1_classification_report.txt` |
| `evaluate_endpoint3.py` | Same pattern for `spatial_features.py`'s held-out evaluation - no retraining. Writes `endpoint3_classification_report.txt` |
| `evaluate_gene_only_vs_spatial.py` | The apples-to-apples comparison: gene-only vs. spatial model predictions on the SAME held-out Xenium cells, including the hard-case (lowest-confidence) breakdown. Writes `endpoint3_vs_gene_only_report.txt` |
| `export_model_eval.py` | Consolidates the three evaluations above into `dashboard/public/model-eval.json` for the dashboard's Model Quality section - no retraining |
| `export_embeddings.py` | Computes the Flex UMAP and reconstructs the Xenium spatial-region predictions, writing `dashboard/public/flex-umap.json` and `xenium-spatial.json` for the dashboard's "Where are the tumor cells?" section - no retraining |
| `endpoint1_classification_report.txt`, `endpoint3_classification_report.txt`, `endpoint3_vs_gene_only_report.txt` | Saved output of the three `evaluate_*.py` scripts above - the actual held-out numbers, committed as evidence rather than left in a terminal scrollback |
| `gene_panel.json`, `xenium_panel_genes.txt`, `*.h5ad`, `*.h5`, `*.gtf.gz`, `metrics_summary.csv` | Raw/intermediate data files (all gitignored — large binary biology data, not source) |
