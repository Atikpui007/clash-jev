import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "export",  // a static site: the replays are files, there is no server
};

export default nextConfig;
