// Get Heal web version
const { version: package_version } = require("./package.json"); // version from package.json
const env_version = process.env.HEAL_VERSION; // version from env variable
// Use env version if set & valid, otherwise default to package version
const version = env_version || package_version;

// PWA is paused. `@ducanh2912/next-pwa` used to wrap this config; it ran a
// second full webpack pass on every build (the duplicate "Compiling for
// server" in the build log) and the package has been unmaintained since
// September 2024. See docs/pwa.md for what was lost and how to bring it back.
//
// public/manifest.json and the AddToHomeScreen prompt stay: installation does
// not need a service worker on iOS, and the prompt is instructional rather
// than driven by `beforeinstallprompt`.

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // `swcMinify` is gone in Next 16 -- Turbopack minifies unconditionally.
  images: {
    unoptimized: true
  },
  output: "standalone",
  // Without this, Turbopack walks up past the repo looking for a lockfile and
  // settles on one in the home directory, then warns that it is outside the
  // repository. Pinning the root keeps inference out of it.
  turbopack: {
    root: __dirname,
  },
  rewrites: async () => {
    // In production, something else (nginx in the one box setup) should take
    // care of this rewrite. TODO (chris): better support setups where
    // web_server and api_server are on different machines.
    if (process.env.NODE_ENV === "production") return [];

    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8080/:path*", // Proxy to Backend
      },
    ];
  },
  redirects: async () => {
    // In production, something else (nginx in the one box setup) should take
    // care of this redirect. TODO (chris): better support setups where
    // web_server and api_server are on different machines.
    const defaultRedirects = [
      {
        source: "/",
        destination: "/chat",
        permanent: true,
      },
    ];

    if (process.env.NODE_ENV === "production") return defaultRedirects;

    return defaultRedirects.concat([
      {
        source: "/api/chat/send-message:params*",
        destination: "http://127.0.0.1:8080/chat/send-message:params*", // Proxy to Backend
        permanent: true,
      },
      {
        source: "/api/query/stream-answer-with-quote:params*",
        destination:
          "http://127.0.0.1:8080/query/stream-answer-with-quote:params*", // Proxy to Backend
        permanent: true,
      },
      {
        source: "/api/query/stream-query-validation:params*",
        destination:
          "http://127.0.0.1:8080/query/stream-query-validation:params*", // Proxy to Backend
        permanent: true,
      },
    ]);
  },
  // Was `publicRuntimeConfig`, which Next 16 removed along with `next/config`.
  // `env` is substituted into the bundle at build time instead, so the value is
  // fixed when the image is built -- which is already how HEAL_VERSION worked,
  // since the Dockerfile bakes it in as a build arg.
  env: {
    HEAL_VERSION: version,
  },
};

module.exports = nextConfig;
