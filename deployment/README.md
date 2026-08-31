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
database already at head. It must never be the thing that applies the Alembic
rebaseline to production: production is **stamped**, not upgraded. The
procedure, including the backup that has to happen first, is in
`docs/architecture-decisions.md` under *Database migrations*.

The database port is not published to the host in production. Use
`docker compose exec relational_db psql -U postgres` for admin access.

## Kubernetes

The manifests in `kubernetes/` are a starting point, not a turnkey production
setup — there is no replication or autoscaling in them.

```bash
kubectl apply -f kubernetes/
```

### Images

All images Heal builds are published under the **`khalifan1126`** Docker Hub
namespace: `khalifan1126/heal-backend` and `khalifan1126/heal-web`. CI pushes
them on a git tag, and the compose files and Kubernetes manifests pull the same
names, so what runs in the cluster is what CI built.

CI needs two repository secrets to push: `DOCKER_USERNAME` (`khalifan1126`) and
`DOCKER_TOKEN` (a Docker Hub access token). Without them the tag-triggered
workflows fail at the login step.

Notes:

- User auth is on by default here, on the assumption this is production. Either
  provide the values in `secrets.yaml` or change `AUTH_TYPE` in
  `env-configmap.yaml`.
- `imagePullPolicy` is `IfNotPresent`. A node-built image is used when one is
  present, and otherwise the image is pulled from Docker Hub. It was `Never`,
  which meant the cluster could only ever run images built on the node itself
  and could never see a CI build.
- HTTPS is assumed to be terminated by your cluster's ingress.
- `kubectl delete -f kubernetes/` **erases the database.** To keep it, delete
  the specific manifests and leave `persistent-volumes.yaml` alone.
- `file-connector-pvc` is still declared but no longer mounted; it went with the
  connectors. It is left in place rather than deleted because removing a PVC
  destroys data.
