FROM node:20-alpine AS build
WORKDIR /ui
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.31-alpine
# The official image renders /etc/nginx/templates/*.template with envsubst (only defined variables, so $uri is untouched).
ARG VITE_API_URL=http://localhost:8000
# IDP_ORIGIN: the SSO provider's origin (e.g. https://login.microsoftonline.com) so the PKCE token exchange is allowed by CSP.
ENV API_ORIGIN=$VITE_API_URL \
    IDP_ORIGIN=""
COPY --from=build /ui/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
