# ide8.flow review UI — vite build served by nginx, /api/* proxied to the
# worker (same contract as the vite dev proxy).
#   docker build -t ide8-ui services/ui
FROM node:22-slim AS build
WORKDIR /ui
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx tsc --noEmit && npm run build

FROM nginx:1.27-alpine
COPY --from=build /ui/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
