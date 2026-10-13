/** @type {import('next').NextConfig} */
const config = {
  // Five sequential 90-second investigations must outlive Next's 30-second proxy default.
  experimental: {proxyTimeout: 500_000},
  async rewrites() {
    return [{source: '/api/:path*', destination: `${process.env.BACKEND_URL || 'http://127.0.0.1:8000'}/api/:path*`}];
  },
  poweredByHeader: false,
};
export default config;
