# syntax=docker/dockerfile:1
FROM python:3.11.7-slim-bookworm

# Image version, normally overridden by the release workflow with the git tag.
# Read by heal_app/__init__.py.
ARG HEAL_VERSION=0.3-dev
ENV HEAL_VERSION=${HEAL_VERSION}
RUN echo "HEAL_VERSION: ${HEAL_VERSION}"

# System dependencies
# cmake             needed to build psycopg (postgres); removed again below
# ca-certificates   HTTPS to the LLM and translation providers
#
# `zip` went with Vespa -- it existed only to package the Vespa app bundle.
# `curl` is deliberately NOT installed: the CVE cleanup below removes
# libldap-2.5-0, which cascades to libcurl4 and takes curl with it. Installing
# it here would only be undone twelve lines later. The container healthcheck
# uses Python instead -- see the compose files.
RUN apt-get update && \
    apt-get install -y cmake ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Install Python dependencies
# The playwright browser install and the `py` CVE cleanup both went with the
# connector packages that needed them. Supervisor went with the background
# fleet, which Phase 1 does not run.
#
# The pip cache is a BuildKit cache mount, NOT a layer: it persists between
# builds and survives a failed one, while adding nothing to the image size.
# This matters because tensorflow-cpu-aws alone is 263 MB. With
# --no-cache-dir, a read timeout at 20 MB threw away every wheel already
# fetched and the next attempt started from zero. Now a retry resumes.
#
# The generous timeout and retry count are for the same reason: pip's 15s
# default read timeout is not enough for a 263 MB wheel on a slow link.
COPY ./requirements/default.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade \
        --timeout 120 \
        --retries 10 \
        -r /tmp/requirements.txt

# The embedding model, baked in at build time.
#
# Downloaded on first use, it put a minute of silence behind the admin's
# "Upload and index" click and made indexing depend on the host having
# internet at that exact moment. 384 dimensions, frozen before first ingest.
#
# HF_HOME points at the baked copy. Overriding HEAL_EMBEDDING_MODEL at runtime
# still works; that model is fetched on demand into the same directory.
ARG HEAL_EMBEDDING_MODEL=thenlper/gte-small
ENV HF_HOME=/opt/models
ENV SENTENCE_TRANSFORMERS_HOME=/opt/models
# The hub publishes this model in five formats. A PyTorch load path opens one
# of them; the CoreML, ONNX (three quantisations) and OpenVINO copies are
# 575 MB of an otherwise 64 MB model. They are never fetched rather than
# fetched and deleted: on a slow link the download is the cost, and a later
# `rm` would not shrink the image anyway -- the fat layer stays and the delete
# only writes whiteouts over it.
#
# sentence-transformers' own snapshot_download takes fnmatch patterns and
# writes to exactly the directory the SentenceTransformer constructor checks,
# downloading modules.json last. So the constructor below finds a complete
# model and downloads nothing. safetensors is skipped too; transformers falls
# back to pytorch_model.bin, which this pinned version reads most predictably.
#
# The cache mount is where the download lands, not the image: writing straight
# to /opt/models made every rebuild of this layer re-fetch everything, the same
# problem the pip cache above solves.
RUN --mount=type=cache,target=/root/.cache/st,sharing=locked \
    HF_HOME=/root/.cache/st SENTENCE_TRANSFORMERS_HOME=/root/.cache/st \
    python -c "from sentence_transformers import SentenceTransformer; \
from sentence_transformers.util import snapshot_download; \
snapshot_download('${HEAL_EMBEDDING_MODEL}', cache_dir='/root/.cache/st', \
library_name='sentence-transformers', \
ignore_files=['coreml/*', 'onnx/*', 'openvino/*', '*.safetensors', \
'tf_model.h5', 'rust_model.ot', 'flax_model.msgpack']); \
SentenceTransformer('${HEAL_EMBEDDING_MODEL}')" && \
    mkdir -p /opt/models && \
    cp -a /root/.cache/st/. /opt/models/ && \
    chmod -R a+rX /opt/models && \
    du -sh /opt/models

# Cleanup for CVEs and size reduction
# perl-base is part of the base Python Debian image but not needed for Heal,
# and could only be removed with --allow-remove-essential.
#
# The tornado test key (https://github.com/tornadoweb/tornado/issues/3107) is
# removed with `-f`: tornado arrived transitively via `distributed`, which went
# with the Dask worker pool, so the file is normally absent now. The line stays
# guarded rather than deleted so the mitigation survives if tornado ever
# returns as somebody else's transitive dependency.
RUN apt-get remove -y --allow-remove-essential perl-base cmake libldap-2.5-0 && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /usr/local/lib/python3.11/site-packages/tornado/test/test.key

# Set up application files
WORKDIR /app
COPY ./heal_app /app/heal_app
# Heal-owned modules. `deprecated/` is deliberately not copied -- nothing in
# the image should be able to import it.
COPY ./heal /app/heal
COPY ./shared_models /app/shared_models
COPY ./alembic /app/alembic
COPY ./alembic.ini /app/alembic.ini

ENV PYTHONPATH /app

# Compose overrides this for the api_server; a bare container is inert.
# Phase 1 runs exactly one process per container -- no supervisord.
CMD ["tail", "-f", "/dev/null"]
