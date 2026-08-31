# syntax=docker/dockerfile:1
FROM node:20-alpine AS base

# Image version, normally overridden by the release workflow with the git tag.
ARG HEAL_VERSION=0.3-dev
ENV HEAL_VERSION=${HEAL_VERSION}
RUN echo "HEAL_VERSION: ${HEAL_VERSION}"

# Step 1. Install dependencies only when needed
FROM base AS deps
# Check https://github.com/nodejs/docker-node/tree/b4117f9333da4138b03a546ec926ef50a31506c3#nodealpine to understand why libc6-compat might be needed.
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Install dependencies based on the preferred package manager
#
# The package manager cache is a BuildKit cache mount, so it persists between
# builds and survives a failed one without adding to the image. Same reason as
# the backend's pip cache: on a slow link a network timeout used to discard
# every package already fetched, and the retry started from zero.
COPY package.json yarn.lock* package-lock.json* pnpm-lock.yaml* ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    --mount=type=cache,target=/usr/local/share/.cache/yarn,sharing=locked \
  npm config set fetch-retries 10 && \
  npm config set fetch-retry-maxtimeout 120000 && \
  if [ -f yarn.lock ]; then yarn --frozen-lockfile --network-timeout 600000; \
  elif [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then yarn global add pnpm && pnpm i --frozen-lockfile; \
  else echo "Lockfile not found." && exit 1; \
  fi

# Step 2. Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Disable automatic telemetry collection
ENV NEXT_TELEMETRY_DISABLED 1

# Environment variables must be present at build time
# https://github.com/vercel/next.js/discussions/14030
# NOTE: if you add something here, make sure to add it to the runner as well
ARG NEXT_PUBLIC_DISABLE_STREAMING
ENV NEXT_PUBLIC_DISABLE_STREAMING=${NEXT_PUBLIC_DISABLE_STREAMING}

RUN npm run build

# Step 3. Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

# Remove global node modules, since they are not needed by the actual app
# (all dependencies are copied over into the `/app` dir itself). These
# global modules may be outdated and trigger security scans.
RUN rm -rf /usr/local/lib/node_modules

# Not needed, set by compose 
# ENV NODE_ENV production  

# Disable automatic telemetry collection
ENV NEXT_TELEMETRY_DISABLED 1

# Don't run production as root
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
USER nextjs

# Add back in if we add anything to `public`
COPY --from=builder /app/public ./public

# Automatically leverage output traces to reduce image size
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Environment variables must be redefined at run time
# NOTE: if you add something here, make sure to add it to the builder as well
ARG NEXT_PUBLIC_DISABLE_STREAMING
ENV NEXT_PUBLIC_DISABLE_STREAMING=${NEXT_PUBLIC_DISABLE_STREAMING}

# Note: Don't expose ports here, Compose will handle that for us if necessary. 
# If you want to run this without compose, specify the ports to 
# expose via cli

CMD ["node", "server.js"]
