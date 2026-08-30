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
COPY ./requirements/default.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /tmp/requirements.txt

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
