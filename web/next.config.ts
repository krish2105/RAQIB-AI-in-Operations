import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import path from "node:path";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["three"],
  // A stray package-lock.json in the home directory otherwise confuses root detection.
  turbopack: { root: path.join(__dirname) },
};

export default withNextIntl(nextConfig);
