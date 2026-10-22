"use client";

import { fetcher } from "@/lib/fetcher";
import useSWR from "swr";

export const HealthCheckBanner = () => {
  const { error } = useSWR("/api/health", fetcher);
  if (!error) {
    return null;
  }

  return (
    <div className="text-xs mx-auto bg-gradient-to-r from-red-900 to-red-700 p-2 rounded-sm border-hidden text-gray-300">
      <p className="font-bold pb-1">Heal is temporarily unavailable.</p>

      <p className="px-1">
        Please try again in a few minutes. If the problem continues, contact
        your administrator.
      </p>
    </div>
  );
};
