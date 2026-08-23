FROM node:24-alpine AS dependencies
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM dependencies AS builder
COPY apps/web ./
RUN npm run build

FROM node:24-alpine AS runner
ENV NODE_ENV=production
WORKDIR /web
COPY --from=builder /web/.next/standalone ./
COPY --from=builder /web/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]

