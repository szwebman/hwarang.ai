FROM node:22-alpine AS builder

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace config
COPY pnpm-workspace.yaml ./
COPY modules/hwarang-web/package.json modules/hwarang-web/

# Install dependencies
WORKDIR /app/modules/hwarang-web
RUN pnpm install --frozen-lockfile

# Copy source
COPY modules/hwarang-web/ .

# Build
RUN pnpm build

FROM node:22-alpine AS runtime

WORKDIR /app

COPY --from=builder /app/modules/hwarang-web/.next/standalone ./
COPY --from=builder /app/modules/hwarang-web/.next/static ./.next/static
COPY --from=builder /app/modules/hwarang-web/public ./public

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
