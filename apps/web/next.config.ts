import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const api = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/v1/:path*", destination: `${api}/v1/:path*` }];
  },
};

export default nextConfig;
