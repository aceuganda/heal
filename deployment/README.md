# Deploying Heal

Heal is five services:

```
  nginx  ->  web_server (Next.js)  ->  api_server (FastAPI)  ->  relational_db (PostgreSQL)
                                              |
                                              +-------------->  qdrant (approved sources)
```

All five start together. Nothing else
runs: there is no scheduler, no queue, no worker pool and no supervisor. See
`docs/runtime-architecture.md` for which services run at each stage, and
`docs/architecture-decisions.md` for why.

The Danswer-era stack — Vespa (`index`), the `background` supervisord fleet and
`model_server` — is frozen in `deployment/deprecated/` and in
`docker_compose/docker-compose.dev.yml`. None of it is deployed.

## Local

From the repository root:

```bash
make up          # build and start all five services; web on :3000
make api-logs    # tail the API server
make smoke       # check every service answers
make down        # stop, keeping volumes
```

There is no second command for the vector store and no knowledge profile:
`make up` starts it, the API creates the collection on boot, and documents are
uploaded and indexed at <http://localhost:3000/admin/sources>.

## Docker Compose, production

Requirements: Docker and Docker Compose.

1. **Configure.** In `docker_compose/`, copy `env.prod.template` to `.env` and
   fill it in, and copy `env.nginx.template` to `.env.nginx`.

   Two settings decide whether Luganda works at all:
   `TRANSLATION_EN_URL` and `TRANSLATION_LUG_URL`. There is no default baked
   into the image, so if they are unset Luganda chat fails with a config error
   naming the variable. English chat is unaffected.

2. **TLS.** Pick one:
   - *Certbot in the stack* — keep `NGINX_CONF_TEMPLATE=app.conf.template`,
     run `chmod +x init-letsencrypt.sh && ./init-letsencrypt.sh` once, then add
     `--profile letsencrypt` to every compose command.
   - *TLS terminated upstream* — set
     `NGINX_CONF_TEMPLATE=app.conf.template.no-letsencrypt` and omit the
     profile. This replaces the old `docker-compose.prod-no-letsencrypt.yml`.

3. **Start.**

   ```bash
   cd docker_compose
   docker compose -f docker-compose.prod.yml -p heal-stack up -d
   # with certbot:
   docker compose -f docker-compose.prod.yml --profile letsencrypt -p heal-stack up -d
   ```

   The first build pulls a large Python image and may take 15+ minutes.

4. **Stop.**

   ```bash
   docker compose -f docker-compose.prod.yml -p heal-stack stop   # stop
   docker compose -f docker-compose.prod.yml -p heal-stack down   # remove containers
   ```

   `down -v` additionally deletes the volumes. **That erases the database —
   every user account and every chat.** Take a `pg_dump` first.

### Database

`api_server` runs `alembic upgrade head` on start. This is a no-op against a
database already at head. The history is the inherited chain with Heal's
migrations appended; it has not been squashed into a new baseline. If one is
ever written, `upgrade` must never be what applies it to production —
production is **stamped**, not upgraded. See `docs/architecture-decisions.md`
under *Schema and migrations*.

The database port is not published to the host in production. Use
`docker compose exec relational_db psql -U postgres` for admin access.

## Kubernetes (k3s)

Deploys run from your machine with `make deploy`, entirely through the k3s
API as the `heal-deployer` service account: no SSH, no sudo, no outside
registry. Nothing builds or deploys from GitHub: GitHub holds the code, and
every deployed commit must already be on its `main`.

```
make deploy
  1. gates   tree clean · HEAD on origin/main · deps pinned, no pre-releases
             · base images pinned to x.y.z or a digest
  2. scan    trivy: fixable CRITICAL/HIGH in shipped deps, leaked secrets
  3. build   both images for DEPLOY_PLATFORM, tagged with the commit;
             architecture checked; trivy scan + CycloneDX SBOM
  4. ask     shows commit, images, platform, cluster, namespace;
             type the namespace
  5. push    to the registry inside k3s, through an API port-forward;
             cosign sign + verify each digest, if keyed
  6. apply   server-side dry run, apply, wait for rollout; a failed
             rollout is undone automatically
  7. record  deployment/.deploy/history.jsonl + the exact manifest applied
```

Other commands: `make deploy-check` (steps 1–2 only), `make deploy-doctor`,
`make deploy-status`, `make deploy-rollback`. `make deploy-unchecked` skips
steps 1–2, the image scan in step 3 and the prompt in step 4 (it deploys to
DEPLOY_NAMESPACE), for a rebuild right after a passing `make deploy-check`;
its history entry says `"checked": false`.

Tools on the deploying machine: `git`, `docker`, `kubectl`, `trivy`, `crane`,
and `cosign` if you sign (`brew install kubectl trivy crane cosign`). The CLI
itself needs only Python 3.

### Architecture

Servers are almost always amd64; an Apple Silicon Mac builds arm64 unless told
otherwise. Every build passes `--platform $DEPLOY_PLATFORM` (default
`linux/amd64`, built under emulation on a Mac -- slower, same result) and is
inspected afterwards: a wrong-architecture image stops the deploy before it
ships, instead of crash-looping on the node with `exec format error`.

### CPU or GPU backend

The backend's PyTorch build is chosen at build time with `TORCH_VARIANT`:

| | `cpu` (default) | `cuda` |
|---|---|---|
| torch from | PyTorch's CPU index (amd64); PyPI (arm64, already CPU-only) | PyPI, which ships the CUDA build on amd64 |
| image size | ~2.5 GB smaller | includes the CUDA libraries |
| set with | `DEPLOY_TORCH_VARIANT` in `deploy.env`, or `TORCH_VARIANT=` in the shell before a Compose build | same |

The build checks which torch it ended up with and fails on a mismatch, so a
`cpu` image never silently carries GPU libraries and a `cuda` image is never
silently CPU-only. The variant is also baked in as `HEAL_TORCH_VARIANT`.

At runtime `HEAL_EMBEDDING_DEVICE` picks where embeddings run: empty uses a
GPU when one is usable and the CPU otherwise; `cpu` or `cuda[:N]` pins it.
Asking for `cuda` where there is no usable GPU stops the API with an error
naming the fix, rather than quietly running on the CPU.

A `cuda` image only gets a GPU on a node that has the NVIDIA driver and
container toolkit (k3s then registers an `nvidia` runtime class), the NVIDIA
device plugin, and a pod spec with `runtimeClassName: nvidia` and an
`nvidia.com/gpu` limit. None of that is in these manifests yet.

### The registry inside k3s

`kubernetes/registry/registry.yaml` runs a private registry that listens on
the node's loopback (`localhost:5050`) only, so nothing on the network can
reach it. The node pulls from it there; the deploy reaches it with `kubectl
port-forward`, which goes through the API and needs the deployer's token, and
pushes with `crane`. Only layers the registry lacks are sent, so after the
first deploy a release is mostly the application layer. Images are deployed
by digest.

The registry keeps every pushed release. Unchanged layers are shared, so it
grows by roughly the changed layers per deploy; its volume is 20 GiB.

### One-time setup

Everything lives in the `heal` namespace. On the server, from a copy of
`deployment/kubernetes/` (fill in `env-configmap.yaml` first):

```bash
sudo ALLOW_FROM=<network>/<mask> TLS_SAN=<name you deploy against> ./setup-server.sh
```

It points containerd at the loopback registry, adds `TLS_SAN` to the API
certificate, opens 6443 to `ALLOW_FROM` only (never the internet), applies
the deployer account and the registry, creates `env-configmap` and
`heal-secrets` (random database password) only if they are missing, and
prints the CA path and the deploy token. Re-running it is safe.

On your machine: copy the CA to `~/.config/heal-deploy/ca.crt`, copy
`deploy.env.template` to `deploy.env`, set `DEPLOY_API_SERVER` and
`DEPLOY_KUBE_TOKEN`, and run `make deploy-doctor`. It checks the tools, that
the API accepts the token, and that the registry is running.

Each command writes a short-lived owner-only kubeconfig from those settings
and deletes it afterwards, so the token never appears on a command line. To
revoke access, delete the `heal-deployer-token` Secret and re-run the script
for a new one.

### What the deployer can and cannot do

It can create and update Deployments, StatefulSets, Services, PVCs and
ConfigMaps in `heal`, read pods, logs and events, and port-forward to pods
(how images reach the registry). It cannot read Secrets, touch any other
namespace, or change its own permissions.

`kustomization.yaml` is the list of what a deploy applies. `env-configmap.yaml`
and `secrets.yaml` are left out on purpose: re-applying the repo templates
would blank the cluster's real settings.

### Exceptions to the scan

A finding with no fixed release does not block (`--ignore-unfixed`). To accept
a fixable one, add its ID to `.trivyignore` at the repo root with a reason and
a revisit date; that file is reviewed like code.

### Notes

- The manifests name images `heal-backend` and `heal-web`; the deploy pins
  them to `registry/image@sha256:…`. A raw `kubectl apply -f kubernetes/` now
  fails to pull instead of running an unscanned `latest`.
- User auth is on by default (`AUTH_TYPE` in `env-configmap.yaml`).
- HTTPS is assumed to be terminated by your cluster's ingress.
- Qdrant runs as `qdrant-statefulset` behind the ClusterIP `qdrant-service`
  (10 GiB volume). It will not start until `heal-secrets` has
  `qdrant_api_key`; on a cluster set up before Qdrant, add it once on the
  server (the deployer cannot write Secrets):
  `sudo k3s kubectl -n heal patch secret heal-secrets -p "{\"stringData\":{\"qdrant_api_key\":\"$(openssl rand -hex 32)\"}}"`.
  Set `QDRANT_URL=http://qdrant-service:6333` in `env-configmap` and leave
  `KNOWLEDGE_ENABLED=false` until the corpus is ingested.
- `kubectl delete -f kubernetes/` **erases the database.** To keep it, delete
  the specific manifests and leave `persistent-volumes.yaml` alone.
- `file-connector-pvc` is still declared but no longer mounted; it is left in
  place because removing a PVC destroys data.

### Docker Hub images (Compose)

The tag-triggered workflows still push `khalifan1126/heal-backend` and
`khalifan1126/heal-web` to Docker Hub for the Compose deployment, using the
`DOCKER_USERNAME` and `DOCKER_TOKEN` repository secrets. The k3s deploy does
not use them.
