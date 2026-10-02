FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.ts reads API_BASE_URL only at request time (server-side fetch
# and the rewrites() destination), not during the build — no build ARG
# needed for it. NEXT_PUBLIC_* variables are the opposite: Next.js inlines
# them into the client bundle at build time, so this one must be supplied
# as a build ARG (see compose.yaml's frontend.build.args).
ARG NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
ENV NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=$NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
RUN npm run build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# output: "standalone" (next.config.ts) traces only the files this app
# needs, so the runtime image doesn't carry the full node_modules tree.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

RUN chown -R 10001:10001 /app
USER 10001:10001

EXPOSE 3000
CMD ["node", "server.js"]
