# The Zyrcle web app (the hackathon UI wired to the new API), served by unprivileged nginx on :8080.
# Build context: apps/web.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_URL=https://zyrcle-backend.deviego.xyz
ARG VITE_SIWE_DOMAIN=zyrcle.deviego.xyz
ARG VITE_CHAIN_ID=20261121
ARG VITE_RPC_URL=https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc
ARG VITE_TREASURY_ADDRESS=0xB843946A42F2791B8b932F8c0205C9D277E351B1
ENV VITE_API_URL=$VITE_API_URL VITE_SIWE_DOMAIN=$VITE_SIWE_DOMAIN VITE_CHAIN_ID=$VITE_CHAIN_ID \
    VITE_RPC_URL=$VITE_RPC_URL VITE_TREASURY_ADDRESS=$VITE_TREASURY_ADDRESS
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
