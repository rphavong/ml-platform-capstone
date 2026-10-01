# Architecture

## Presentation overview (start here)

The simple version — what a reviewer needs on one slide. A draw.io file of this exact
diagram is at [`ARCHITECTURE-PRESENTATION.drawio`](ARCHITECTURE-PRESENTATION.drawio).

```mermaid
flowchart LR
    dev["Developer"] -->|git push| gha["GitHub Actions\ntest → build → deploy"]
    gha -->|build & push image| ecr[("Container Registry\n(ECR)")]
    ecr -.image pull.-> eks["Kubernetes (EKS)\n3 proxy services"]
    gha -->|deploy| eks
    eks -->|routes requests| sm["Amazon SageMaker\n3 ML model endpoints"]
    dash["React Dashboard\nstatus, test predictions,\nmodel-quality evidence"] -->|health + predictions| eks
```

## Full detail (for Q&A / engineering reference)

Every namespace, ConfigMap, Secret and the 3 endpoints individually — useful when
someone asks "which namespace is which" or "how do credentials actually flow," not
for a slide. A draw.io version of THIS diagram (the dense one) is at
[`ARCHITECTURE.drawio`](ARCHITECTURE.drawio) — open it at
[app.diagrams.net](https://app.diagrams.net) (File → Open From → Device) or in the
draw.io VS Code extension for an easier-to-navigate, pan/zoomable view with the same
containers and connections.

```mermaid
flowchart TB
    subgraph dev["Developer"]
        push["git push to main"]
    end

    subgraph gha["GitHub Actions (.github/workflows/)"]
        test["test.yml\npytest per service"]
        build["cd.yml: build-and-push\ndocker buildx -> ECR"]
        deploy["cd.yml: deploy\nkubectl set image + rollout status\n+ live /health verification"]
        test --> build --> deploy
    end

    subgraph aws["AWS (us-east-1, Terraform-managed)"]
        ecr[("ECR\n3 repos, :k8s-proxy + :sha tags")]

        subgraph eks["EKS cluster: assessment4-robert-cluster"]
            subgraph ns1["namespace: single-cell-genomics"]
                svc1["endpoint1-flex\nDeployment + Service"]
                svc2["endpoint2-xenium\nDeployment + Service"]
                q1["ResourceQuota + LimitRange"]
                cm1["ConfigMap: proxy-config"]
                sec1["Secret: sagemaker-invoke-fallback"]
            end
            subgraph ns2["namespace: spatial-analysis"]
                svc3["endpoint3-spatial\nDeployment + Service"]
                q2["ResourceQuota + LimitRange"]
                cm2["ConfigMap: proxy-config"]
                sec2["Secret: sagemaker-invoke-fallback"]
            end
        end

        subgraph sm["SageMaker (BYOC endpoints)"]
            sm1["assessment4-robert-\nendpoint1-flex\n(shared reference model)"]
            sm2["assessment4-robert-\nendpoint2-xenium\n(SAME model as endpoint1)"]
            sm3["assessment4-robert-\nendpoint3-spatial\n(separately-trained,\n+ neighborhood features)"]
        end
    end

    subgraph client["React Ops Dashboard (dashboard/)"]
        dash["Health polling, test-prediction trigger,\nModel Quality + Cell Maps evidence"]
    end

    push --> gha
    build --> ecr
    deploy --> eks
    ecr -.image pull via node IAM role.-> eks

    svc1 -- "invoke_endpoint\n(node IAM role, or\nSecret fallback)" --> sm1
    svc2 -- "invoke_endpoint" --> sm2
    svc3 -- "invoke_endpoint" --> sm3

    dash -- "direct browser calls\n/health /ready /predict" --> svc1
    dash --> svc2
    dash --> svc3
```

**Explicit routing:** each proxy service reads its target SageMaker endpoint name from
its namespace's `ConfigMap` via an env var (`SAGEMAKER_ENDPOINT_NAME`) — a request to
`endpoint3-spatial` can only ever reach `assessment4-robert-endpoint3-spatial`, visible
directly in the manifest without opening any code.

**Credentials:** pods get AWS credentials primarily from the EKS node's IAM role (via
IMDS — see [Design Decisions](DESIGN_DECISIONS.md) for why hop-limit mattered here),
with a scoped-down (`sagemaker:InvokeEndpoint`-only, 3-endpoints-only) IAM user's keys
in a Kubernetes `Secret` as an explicit, code-level fallback if the primary path is
ever unavailable.

See [README.md](README.md) for the business scenario and endpoint details, and
[REPOSITORY_LAYOUT.md](REPOSITORY_LAYOUT.md) for what every file pictured above
actually is.
