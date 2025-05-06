// Get Danswer Web Version
const { version: package_version } = require("./package.json"); // version from package.json
const env_version = process.env.DANSWER_VERSION; // version from env variable
// Use env version if set & valid, otherwise default to package version
const version = env_version || package_version;

/** @type {import('next').NextConfig} */
const withPWA = require("@ducanh2912/next-pwa").default({
  dest: "public",
  cacheOnFrontEndNav: true,
  aggressiveFrontEndNavCaching: true,
  reloadOnOnline: true,
  swcMinify: true,
  workboxOptions: {
    disableDevLogs: true,
  },
});
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    unoptimized: true
  },
  output: "standalone",
  rewrites: async () => {
    // In production, something else (nginx in the one box setup) should take
    // care of this rewrite. TODO (chris): better support setups where
    // web_server and api_server are on different machines.
    //temp
    // if (process.env.NODE_ENV === "production") return [];
    // console.log("Rewrites: ", process.env.NODE_ENV);
    return [
      {
        source: "/api/:path*",
        destination: "http://135.181.63.203:8080/:path*", // Proxy to Backend
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

    //temp

    // if (process.env.NODE_ENV === "production") return defaultRedirects;

    // console.log("Rewrites: ", process.env.NODE_ENV);

    return defaultRedirects.concat([
      {
        source: "/api/chat/send-message:params*",
        destination: "http://135.181.63.203:8080/chat/send-message:params*", // Proxy to Backend
        permanent: true,
      },
      {
        source: "/api/query/stream-answer-with-quote:params*",
        destination:
          "http://135.181.63.203:8080/query/stream-answer-with-quote:params*", // Proxy to Backend
        permanent: true,
      },
      {
        source: "/api/query/stream-query-validation:params*",
        destination:
          "http://135.181.63.203:8080/query/stream-query-validation:params*", // Proxy to Backend
        permanent: true,
      },
    ]);
  },
  publicRuntimeConfig: {
    version,
  },
};

module.exports = withPWA(nextConfig);
