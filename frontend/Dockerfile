# --- production build: the static app, API on the same origin (/api) -------
# Declared before `dev` on purpose: docker-compose.yml builds this file with no target, which
# means the LAST stage — dev must stay last so the dev stack is unchanged.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Same-origin API behind nginx: works on the PC (localhost) and from phones on the farm network
# (http://<pc-ip>:<port>) without CORS or a hard-coded host.
ENV VITE_API_URL=/api
RUN npm run build

# --- production image: nginx serving the build and proxying /api to Django ----
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

# --- dev image: Vite dev server, live reload against a bind-mounted src ----
FROM node:22-slim AS dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY --chown=node:node . .
RUN chown -R node:node /app

USER node
EXPOSE 5173

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -f http://localhost:5173/ || exit 1

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
