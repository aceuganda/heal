import { buildUrl } from "./utilsSS";

// Next 16 removed `next/config` and `publicRuntimeConfig`. next.config.js now
// inlines the same value through `env`, which is substituted at build time.
const version = process.env.HEAL_VERSION;

// Maybe improve type-safety by creating a 'VersionType' instead of generic string
export const getBackendVersion = async (): Promise<string | null> => {
  try {
    const res = await fetch(buildUrl("/version"));
    if (!res.ok) {
      //throw new Error("Failed to fetch data");
      return null;
    }

    const data: { backend_version: string } = await res.json();
    return data.backend_version as string;
  } catch (e) {
    console.log(`Error fetching backend version info: ${e}`);
    return null;
  }
};

// Frontend?
export const getWebVersion = (): string | null => {
  // `process.env` is `string | undefined`; the old publicRuntimeConfig read was
  // untyped, so this narrowing is new rather than a behaviour change.
  return version ?? null;
};
