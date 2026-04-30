import type { NextConfig } from "next";

const nextConfig = {
  /* config options here */
  
  // In Next 16, use 'eslint' and 'typescript' like this 
  // but cast the object to keep TS happy
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
} as NextConfig; // Casting at the end allows these properties to exist

export default nextConfig;