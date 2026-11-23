# The Zyrcle web app (the hackathon UI wired to the new API), served by unprivileged nginx on :8080.
# Build context: the repository root (the app imports packages/client):
#   docker build -f apps/web/Dockerfile .
FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a AS build
WORKDIR /repo/apps/web
COPY packages/client /repo/packages/client
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
ARG VITE_API_URL=https://zyrcle-backend.deviego.xyz
ARG VITE_SIWE_DOMAIN=zyrcle.deviego.xyz
ARG VITE_CHAIN_ID=20261121
ARG VITE_RPC_URL=https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc
ARG VITE_TREASURY_ADDRESS=0xd7052201140224018b123ecFF7b83B4251790Aeb
# Its origin must also be in security-headers.conf (connect-src).
ARG VITE_IPFS_GATEWAY=https://gateway.pinata.cloud/ipfs/
ENV VITE_API_URL=$VITE_API_URL VITE_SIWE_DOMAIN=$VITE_SIWE_DOMAIN VITE_CHAIN_ID=$VITE_CHAIN_ID \
    VITE_RPC_URL=$VITE_RPC_URL VITE_TREASURY_ADDRESS=$VITE_TREASURY_ADDRESS \
    VITE_IPFS_GATEWAY=$VITE_IPFS_GATEWAY
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY apps/web/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
