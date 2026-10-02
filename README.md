# ML Platform Capstone — Multi-Endpoint Cervical Cancer Cell Classification

Internal ML platform delivery for Code Platoon AICO Assessment IV: Terraform-provisioned
AWS infrastructure, three SageMaker endpoints orchestrated behind FastAPI proxy services
on EKS, an automated GitHub Actions CI/CD pipeline, and a React ops dashboard — built
around a real cervical cancer single-cell + spatial transcriptomics dataset instead of
the assessment's three example business scenarios (see [Business Scenario](#business-scenario)
below for why, and for the case that this satisfies the assessment's actual intent).

**Author:** Robert Phavong · Code Platoon AICO · `assessment4-robert-*` in the shared class AWS account

---

## Table of Contents

1. [Business Scenario](#business-scenario)
2. [The Three Endpoints](#the-three-endpoints)
3. [Setup, Deploy, Verify, Teardown](#setup-deploy-verify-teardown)
4. [Pushing Changes & Triggering CI/CD](#pushing-changes--triggering-cicd)
5. [Dashboard Evidence: Model Quality & Cell Maps](#dashboard-evidence-model-quality--cell-maps)
6. [Further Reading](#further-reading)

---

## Business Scenario

The assessment offers three example scenarios (Fraud/Recs/Forecasting; three client
contracts; three LLM-tooling teams). This project uses a **different, custom scenario**
instead, built around real public data:

> You're on a platform engineering team inside a cancer research core facility. Two
> wet-lab teams generate single-cell and spatial data from the same tumor sample using
> different 10x Genomics technologies, and each needs a live cell-classification
> endpoint their own analysis pipelines can call:
> - **Single-Cell Genomics team** — runs 10x Genomics **Flex** (whole-transcriptome,
>   dissociated single-cell) data through a malignancy/cell-type classifier, and also
>   serves **Xenium** (targeted spatial) single-cell calls through the same reference
>   model, since both technologies were profiled on a gene panel this model was
>   deliberately trained to generalize across.
> - **Spatial Analysis team** — runs the same tumor's Xenium data through a *second,
>   separately-trained* classifier that adds physical tissue context (what cell types
>   surround a given cell) on top of gene expression, because spatial organization
>   carries real diagnostic signal gene expression alone doesn't — this is the actual
>   reason spatial transcriptomics exists as a technique.

The underlying data is real: the [10x Genomics Cervical Cancer Flex dataset](https://www.10xgenomics.com)
(`9k_Cervical_Cancer_scFFPE_count_filtered_feature_bc_matrix.h5`) and a matched **Xenium
Prime 5K** spatial dataset of cervical cancer FFPE tissue, both public 10x Genomics
datasets of the same tissue type. `ec2-pipeline-pulled/` holds the full from-scratch
biology pipeline — QC, clustering, CNV-based malignancy calling, marker-gene annotation,
spatial neighborhood feature engineering, and model training — that produced every
model artifact the platform serves.

This still satisfies every structural requirement the example scenarios are meant to
demonstrate: multiple internal teams, each with an owned SageMaker endpoint and FastAPI
service, orchestrated and monitored through one shared platform. What's different is the
*content* of the scenario, not its shape.

---

## The Three Endpoints

| | endpoint1-flex | endpoint2-xenium | endpoint3-spatial |
|---|---|---|---|
| Namespace | `single-cell-genomics` | `single-cell-genomics` | `spatial-analysis` |
| Data source | 10x Flex, dissociated single-cell | 10x Xenium Prime 5K, spatial | 10x Xenium Prime 5K, spatial |
| Model | `endpoint1_model.joblib` (XGBoost) | **same file**, same SageMaker model artifact | `endpoint3_model.joblib` (XGBoost, separately trained) |
| Features | Flex genes ∩ Xenium panel genes | same feature set | gene features **+** 10-nearest-physical-neighbor class-composition features |
| Trained in | `ec2-pipeline-pulled/train_classifier.py` | (shares endpoint1's training run) | `ec2-pipeline-pulled/spatial_features.py` |

### Why endpoint1 and endpoint2 use the same model but DON'T return identical predictions

Endpoint1 and endpoint2 are genuinely the same trained model
(`endpoint1_model.joblib`/`endpoint1_label_encoder.joblib`, one XGBoost classifier
trained in `train_classifier.py` on real Flex data, features restricted to
`shared_genes = Flex ∩ Xenium panel genes` so it's valid on data from either
technology) — but each endpoint's "Run test prediction" button sends it a genuinely
different sample:

- **endpoint1's** `test_payload.json` (`ec2-pipeline-pulled/make_flex_test_payload.py`)
  is 5 real **Flex** cells pulled from the exact held-out 20% split
  `train_classifier.py` evaluated against — cells the model never trained on — along
  with both the ground-truth label and the model's own prediction for each.
- **endpoint2's** `test_payload.json` (`ec2-pipeline-pulled/make_test_payloads.py`) is 5
  real **Xenium** cells.

Same model, different real input per technology ⇒ the two buttons will generally
disagree now, which is the honest demonstration of "one reference classifier, valid
across both technologies" — not two buttons that happen to echo each other because
they were fed byte-identical data. (Earlier in this project's development both
buttons *did* send the same Xenium-derived payload, which produced identical output
by construction rather than by design — fixed via the scripts above.)

### Why endpoint3 returns 60 predictions per test run

`spatial_features.py` trains a genuinely different model on `xenium_region.h5ad` (a
spatially-resolved slice of the same Xenium sample), using gene expression **plus**
engineered neighborhood features: for each cell, what fraction of its 10 nearest
*physical* neighbors (`squidpy.gr.spatial_neighbors(n_neighs=10)`) belong to each
predicted class. At inference time, `sagemaker_serve.py` for endpoint3 rebuilds that
spatial graph from whatever batch of cells it's sent — each cell needs x/y coordinates
and an upstream predicted label, and needs at least 11 cells to build a valid
10-neighbor graph. `endpoint3-spatial/model_artifacts/test_payload.json` is a real
60-cell slice from that Xenium spatial region, so "Run test prediction" returns 60
predictions because that's the real batch size packaged for it — not a fixed constant.
The varied labels/confidences across those 60 cells reflect real tumor-dense vs. stroma
vs. immune-rich neighborhoods in that tissue region, which is the actual point of
endpoint3: cells that look identical by gene expression alone can get different, more
accurate calls once physical context is added.

---

## Setup, Deploy, Verify, Teardown

### Prerequisites

- AWS CLI configured against the class account, `terraform`, `kubectl`, `docker`, Python 3.11
- `aws sts get-caller-identity` to confirm credentials before doing anything else

### 0. Local environment (Python venv + dashboard)

Run everything below from the repo root (`ml-platform-capstone/`), with these two
environments active. Mixing them up (e.g. running a Python script with the venv not
activated, or from the wrong working directory) is the most common reason a step that
worked before suddenly "doesn't function" during a demo.

- **Python venv** — one shared virtualenv at the repo root (`venv/`) already has
  everything the Terraform/SageMaker packaging scripts and the
  `ec2-pipeline-pulled/` biology pipeline need (`boto3`, `xgboost`, `scikit-learn`,
  `pandas`, `numpy`, `fastapi`, `geopandas`, plus `anndata`/`scanpy`/`squidpy`/
  `umap-learn` once installed per [Dashboard Evidence](#dashboard-evidence-model-quality--cell-maps)
  below). Activate it **once per terminal, from the repo root**, before running any
  `python ...` command anywhere in this README:
  ```bash
  cd ml-platform-capstone        # repo root
  source venv/bin/activate
  which python                   # sanity check — should resolve inside venv/bin
  ```
  Activation stays on for that terminal session even after you `cd` into a
  subfolder (`sagemaker-packaging/endpoint1-byoc`, `ec2-pipeline-pulled`, etc.) — you
  do **not** need to re-activate per subfolder, just per new terminal tab/window.
- **Dashboard (Node/npm)** — separate from the Python venv, lives entirely under
  `dashboard/`. `npm install` only needs to run once (or again after a
  `package.json` change) — see [Setup step 5](#5-run-the-dashboard).

### 1. Infrastructure (Terraform)

```bash
cd terraform
terraform init
terraform plan -refresh=false -out=tfplan   # see note below on -refresh=false
terraform apply "tfplan"
```

> **Why `-refresh=false`:** this class AWS account's IAM user doesn't have
> `iam:ListAccessKeys`, which Terraform's routine state refresh needs to check on
> existing `aws_iam_access_key` resources. Skipping refresh avoids that wall; nothing
> about those resources changes between runs anyway. Without an account permission
> fix, a normal `terraform plan`/`apply` will error on this.

```bash
aws eks update-kubeconfig --region us-east-1 --name assessment4-robert-cluster
```

### 2. Package and deploy the 3 SageMaker endpoints

```bash
cd sagemaker-packaging/endpoint1-byoc && python package_and_deploy.py && cd ../..
cd sagemaker-packaging/endpoint2-byoc && python package_and_deploy.py && cd ../..
cd sagemaker-packaging/endpoint3-byoc && python package_and_deploy.py && cd ../..
```
#### Run the following to check the endpoints status in AWS:
```bash
aws sagemaker list-endpoints --region us-east-1 --query "Endpoints[*].[EndpointName,EndpointStatus]" --output table
```

Each script builds the model image's artifact bundle, uploads it, and deploys/waits for
`InService`, then runs one real `invoke_endpoint` call against known test data as a
smoke test. Safe to rerun any time — see `package_and_deploy.py` in
[REPOSITORY_LAYOUT.md](REPOSITORY_LAYOUT.md).

### 3. Deploy to Kubernetes

```bash
kubectl apply -f k8s/00-namespaces.yaml
kubectl apply -f k8s/01-configmap-single-cell-genomics.yaml
kubectl apply -f k8s/01-configmap-spatial-analysis.yaml
kubectl apply -f k8s/05-quota-single-cell-genomics.yaml
kubectl apply -f k8s/06-quota-spatial-analysis.yaml
./k8s/create-fallback-secret.sh
kubectl apply -f k8s/02-endpoint1.yaml
kubectl apply -f k8s/03-endpoint2.yaml
kubectl apply -f k8s/04-endpoint3.yaml
```

### 4. Verify

```bash
kubectl get pods -n single-cell-genomics
kubectl get pods -n spatial-analysis
kubectl get resourcequota -n single-cell-genomics
kubectl get resourcequota -n spatial-analysis
```

Look for `1/1 Running` on all 3 pods. From then on, every push to `main` re-verifies
this automatically via `cd.yml`'s `deploy` job (`rollout status` + a live `/health`
check inside the new pod).

### 5. Run the dashboard

```bash
kubectl port-forward -n single-cell-genomics svc/endpoint1-flex 8001:80 &
kubectl port-forward -n single-cell-genomics svc/endpoint2-xenium 8002:80 &
kubectl port-forward -n spatial-analysis svc/endpoint3-spatial 8003:80 &
cd dashboard && npm install && npm run dev
```

Full setup detail (CORS, generating sample payloads) is in `dashboard/README.md`.

### 6. Teardown (cost hygiene between sessions)

```bash
cd sagemaker-packaging/endpoint1-byoc && python package_and_deploy.py --teardown-only && cd ../..
cd sagemaker-packaging/endpoint2-byoc && python package_and_deploy.py --teardown-only && cd ../..
cd sagemaker-packaging/endpoint3-byoc && python package_and_deploy.py --teardown-only && cd ../..
```

Deletes the live SageMaker endpoint/config/model for all 3 (stops the hourly charge)
while keeping the S3 artifact and ECR image, so redeploying before the next session is
fast. The EKS cluster and Kubernetes objects are left running — full `terraform destroy`
is available but not part of the normal between-session cycle for this project.

---

## Dashboard Evidence: Model Quality & Cell Maps

The dashboard (Setup step 5) isn't just a health-check panel — two sections below the
service status cards make the actual model quality visible, not just that the pipes
are connected:

- **Model Quality** — held-out classification accuracy for the endpoint1/2 shared
  model (evaluated on Flex, the only data with independent ground truth) and the
  endpoint3 spatial model, plus a dedicated comparison showing whether adding spatial
  context actually changes predictions — and specifically whether it changes them more
  on the cells the gene-only model itself was least confident about (it does: ~21% of
  the hardest cells flip, vs ~12% overall).
- **Where are the tumor cells?** — a Flex UMAP (feature-space embedding, with a
  toggle between the real annotation and the model's own prediction) and a Xenium
  panel using **actual physical tissue coordinates**, not an embedding (with a toggle
  between the gene-only call and the spatial-aware call) — so you can see geographically
  where spatial context changes the map. Both have a clickable legend to hide/show
  individual classes, and a toggle between a simplified tumor-vs-normal view and the
  full cell-type breakdown.

Both sections read static, pre-computed JSON (`dashboard/public/model-eval.json`,
`flex-umap.json`, `xenium-spatial.json`) rather than live endpoints, since these are
offline held-out evaluations, not something to recompute on every page load. Regenerate
them any time after retraining or re-deriving data:

```bash
cd ec2-pipeline-pulled
pip install anndata scikit-learn squidpy scanpy umap-learn   # one-time, see each script's docstring
python export_model_eval.py      # -> dashboard/public/model-eval.json
python export_embeddings.py      # -> dashboard/public/flex-umap.json, xenium-spatial.json
```

None of these retrain anything — they reload the already-deployed model artifacts and
only predict, so there's zero risk to what's live on SageMaker.

---

## Pushing Changes & Triggering CI/CD

This is a single-author capstone, so changes push straight to `main` rather than
going through pull requests — and that's exactly what `cd.yml` is wired to listen
for (`on: push: branches: [main]`). From the repo root, with the venv active where
Python files changed (see [Local environment](#0-local-environment-python-venv--dashboard)
above):

```bash
git status                  # see what changed
git add -A                  # or add specific files
git commit -m "..."         # describe the change
git push                    # pushes to origin/main — this is what fires GitHub Actions
```

That `git push` to `main` is the trigger. Once it lands on GitHub, `cd.yml` runs,
in order, for all 3 services:

1. **`test`** — calls the shared `test.yml` (pytest against each proxy service). If
   any test fails, the pipeline stops here — nothing gets built or deployed.
2. **`build-and-push`** — builds each service's Docker image and pushes it to its
   ECR repo, tagged both `:k8s-proxy` and `:<commit-sha>`.
3. **`deploy`** — `kubectl set image` onto the live EKS deployment, waits for
   `rollout status` to report success, then calls `/health` *inside* the new pod
   as a live check — not just trusting that the image swap was accepted.

Watch it run from the GitHub repo's **Actions** tab, or `gh run watch` if the
GitHub CLI is installed locally. A red ✗ on `test` or `build-and-push` means
nothing new reached the cluster — the previous image is still running, untouched.

Opening a pull request instead of pushing straight to `main` only runs `ci.yml`
(the same `test.yml` job, nothing else) — a safe way to get test feedback on a
change without building images or touching the live cluster.

---

## Further Reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — the end-to-end flowchart (dev → CI/CD → ECR → EKS
  → SageMaker → dashboard), explicit routing, and how pods get AWS credentials.
- [REPOSITORY_LAYOUT.md](REPOSITORY_LAYOUT.md) — a table of every file in this repo and
  what it does.
- [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) — the non-obvious trade-offs made along the
  way (IMDSv2 hop limit, node-role vs. IRSA, the Secret-backed credential fallback,
  namespace-per-team mapping, and more) — worth reading before Q&A.
