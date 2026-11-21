# CI/CD Pipeline on Kubernetes

A personal DevOps project: a Jenkins pipeline that builds a Docker image, pushes it to a private registry and deploys it to a Kubernetes cluster, with health checks, automatic rollback and log capture when a release fails. Everything runs locally in containers (Jenkins, a `kind` Kubernetes cluster and a `registry:2` image registry), so it costs nothing to run and can be rebuilt from this repo.

![Status](https://img.shields.io/badge/status-in%20progress-yellow) ![Jenkins](https://img.shields.io/badge/CI-Jenkins-red) ![Kubernetes](https://img.shields.io/badge/Kubernetes-kind-blue) ![Docker](https://img.shields.io/badge/Docker-registry%3A2-2496ED)

## What it does

1. A push to GitHub triggers a Jenkins build (manual trigger for now, see Future improvements).
2. Jenkins builds a Docker image tagged with the build number, so every release is traceable.
3. The image is pushed to a local registry.
4. The Deployment is updated to that exact tag with a rolling update.
5. Readiness probes gate the rollout. If the new pods never become ready, the pipeline fails.
6. On failure, Jenkins prints pod status, events and logs, then rolls back to the previous release.

## Architecture

```
 Developer ──push──> GitHub ──checkout──> Jenkins (container, :8081)
                                              │
                          docker build / push │ kubectl apply
                                              ▼
                    ┌─────────────────────────────────────────┐
                    │ Docker network "kind"                   │
                    │                                         │
                    │  kind-registry :5000  <── image pull ── │
                    │                                         │
                    │  cicd-control-plane (Kubernetes 1.31)   │
                    │    Deployment cicd-demo (2 replicas)    │
                    │    Service NodePort 30080 ──> Flask :5000
                    └─────────────────────────────────────────┘
                                              │
                         http://localhost:30080 (host)
```

## Tech stack

| Area | Tool |
|---|---|
| CI/CD | Jenkins (declarative pipeline, Jenkinsfile in repo) |
| Containers | Docker |
| Registry | `registry:2` running locally at `localhost:5001` |
| Orchestration | Kubernetes via `kind` v0.24 (Kubernetes 1.31) |
| App | Python 3.12, Flask |
| Source control | Git, GitHub |

## Repository structure

```
cicd-k8s-project/
├── app.py                 # Flask app with / and /health endpoints
├── requirements.txt
├── Dockerfile             # App image
├── Jenkinsfile            # Pipeline: build, push, deploy, verify, rollback
├── kind-config.yaml       # kind cluster + registry config + port 30080 mapping
├── k8s/
│   ├── deployment.yaml    # 2 replicas, rolling update, probes, resource limits
│   └── service.yaml       # NodePort 30080
└── jenkins/
    └── Dockerfile         # Jenkins image with Docker CLI and kubectl
```

## Prerequisites

- Linux (developed on Ubuntu) with Docker Engine or Docker Desktop
- `kubectl` and `kind`
- Git and a GitHub account (a public repo, so Jenkins can clone it without credentials)

## Quick start

### 1. Run the app locally

```bash
docker build -t cicd-demo:v1 .
docker run -d -p 5000:5000 --name demo cicd-demo:v1
curl localhost:5000/health        # {"status":"ok"}
docker rm -f demo
```

### 2. Start the registry and the cluster

```bash
docker run -d --restart=always -p 127.0.0.1:5001:5000 --name kind-registry registry:2
kind create cluster --name cicd --config kind-config.yaml

for node in $(kind get nodes --name cicd); do
  docker exec "$node" mkdir -p "/etc/containerd/certs.d/localhost:5001"
  printf '[host."http://kind-registry:5000"]\n' | docker exec -i "$node" sh -c 'cat > "/etc/containerd/certs.d/localhost:5001/hosts.toml"'
done
docker network connect kind kind-registry
```

### 3. Deploy by hand (optional check)

```bash
docker build -t localhost:5001/cicd-demo:v1 .
docker push localhost:5001/cicd-demo:v1
sed "s|image: .*|image: localhost:5001/cicd-demo:v1|" k8s/deployment.yaml | kubectl apply -f -
kubectl apply -f k8s/service.yaml
curl http://localhost:30080/health
```

### 4. Run Jenkins

```bash
docker build -t jenkins-cicd jenkins/
docker run -d --name jenkins --restart=unless-stopped -u root \
  -p 8081:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  jenkins-cicd
docker network connect kind jenkins

# give Jenkins a kubeconfig that reaches the cluster over the kind network
kind get kubeconfig --internal --name cicd > /tmp/kubeconfig-internal
docker exec jenkins mkdir -p /var/jenkins_home/.kube
docker cp /tmp/kubeconfig-internal jenkins:/var/jenkins_home/.kube/config
rm /tmp/kubeconfig-internal

# unlock Jenkins at http://localhost:8081
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Create a **Pipeline** job named `cicd-demo` with **Pipeline script from SCM**, your repo URL, branch `*/master` and script path `Jenkinsfile`, then click **Build Now**.

> Security note: Jenkins runs as root with the host Docker socket mounted. That is acceptable for a local lab and should never be done on a shared or public server.

## Pipeline stages

| Stage | What it does |
|---|---|
| Checkout | Clones the repo from GitHub |
| Build image | `docker build` tagged `localhost:5001/cicd-demo:<build number>` |
| Push image | Pushes the tag to the local registry |
| Deploy | Applies the Deployment with the new image tag in a single step, then waits for the rollout (90 s timeout) |
| Verify | Lists pods and calls `/health` through the NodePort |
| Post: failure | If a deploy started: print pod status, events and logs, then `kubectl rollout undo` |
| Post: success | Prints the deployed build number |

### Why the deploy is a single `kubectl apply`

An earlier version ran `kubectl apply -f k8s/` and then `kubectl set image`. The apply reset the image to the manifest's tag and created one revision, and `set image` created a second. A later `rollout undo` therefore returned to the reset revision (`:v1`) instead of the previous build. Rendering the image tag into the manifest before a single apply gives one revision per build, so rollback goes back to the previous build.

## Health checks and safe rollouts

- **Readiness probe** on `/health` keeps traffic away from pods that are not healthy.
- **Liveness probe** restarts hung pods.
- **Rolling update** with `maxUnavailable: 0` and `maxSurge: 1`: old pods keep serving until new pods are ready, so a bad release does not cause downtime.
- **Resource requests and limits** on the container.

## Rollback and troubleshooting

```bash
kubectl get pods                                   # status of pods
kubectl describe pod <pod>                         # events: probe failures, image pull errors
kubectl logs <pod>                                 # application errors
kubectl rollout history deployment/cicd-demo       # revisions
kubectl rollout history deployment/cicd-demo --revision=N | grep Image
kubectl rollout undo deployment/cicd-demo          # manual rollback
kubectl get deployment cicd-demo -o wide           # which image is live
```

| Symptom | Likely cause | Where to look |
|---|---|---|
| `ImagePullBackOff` | Wrong image name/tag, or registry not linked to the cluster | `kubectl describe pod`, Events |
| `CrashLoopBackOff` | App crashes on start | `kubectl logs <pod>` |
| Pod `Running` but `0/1` | Readiness probe failing | `kubectl describe pod`, Events |
| Jenkins cannot reach the cluster | Jenkins not on the `kind` network, or wrong kubeconfig | `docker network connect kind jenkins`, redo kubeconfig copy |
| `Unable to find Jenkinsfile` | Not pushed, wrong branch, or wrong script path | GitHub file list, job configuration |

## Failure experiments

Releases were broken on purpose to test the rollback and practise finding root causes.

| # | Experiment | Symptom | Where I looked | Root cause | Result |
|---|---|---|---|---|---|
| 1 | App raises an exception on startup | Deploy stage timed out, build failed | Console output, pod status, events, pod logs | `RuntimeError` at startup (visible in pod logs) | Rollback ran automatically; old pods kept serving. First run exposed the double-revision issue described above, fixed in the Jenkinsfile |
| 2 | `/health` returns HTTP 500 | _planned_ | _planned_ | Expected: readiness probe failures in pod events | _planned_ |
| 3 | Non-existent image tag | _planned_ | _planned_ | Expected: `Failed to pull image ... not found` in pod events | _planned_ |

## Screenshots

- Jenkins stage view of a successful build: _add screenshot_
- Console output of a failed deploy with diagnostics and rollback: _add screenshot_
- `kubectl get pods` during a rolling update: _add screenshot_

## Lessons learned

- A rollback only helps if the revision history is clean. Two `kubectl` writes per deploy meant rollback landed on the wrong version.
- Pod events (`kubectl describe`) show why Kubernetes is unhappy; pod logs show why the app is unhappy. Check both.
- `localhost` means different things on the host, inside Jenkins and inside the cluster. Jenkins reaches the cluster by container name over the `kind` network.
- A pipeline that runs diagnostics before rolling back leaves evidence in the build log instead of losing it.
- Editing the wrong file (a Service manifest pasted into `deployment.yaml`) produced a misleading image pull error. Verify file contents with `cat` or `grep` before debugging deeper.

## Cost and cleanup

Everything runs locally, so there is no cloud cost. To remove it all:

```bash
kind delete cluster --name cicd
docker rm -f jenkins kind-registry
docker volume rm jenkins_home
```

## Future improvements

- GitHub webhook trigger (needs a tunnel such as ngrok for a local Jenkins)
- Automated tests stage before the image is built
- Image vulnerability scan (for example Trivy) before pushing
- Helm chart or Kustomize instead of `sed` for rendering the image tag
- Run on a cloud cluster (k3s on EC2 or EKS) as an optional extension
- Slack or email notifications on failure

## Author

Sohan Sahoo, [github.com/sahoosohan](https://github.com/sahoosohan)
