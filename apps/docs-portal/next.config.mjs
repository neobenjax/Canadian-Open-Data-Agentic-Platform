import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: process.env.STANDALONE_BUILD === '1' ? 'standalone' : undefined,
};

export default withMDX(nextConfig);
