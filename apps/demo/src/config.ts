const env = import.meta.env;

export const API_URL: string = env.VITE_API_URL ?? "http://127.0.0.1:8000";
export const RPC_URL: string =
  env.VITE_RPC_URL ??
  "https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc";
export const CHAIN_ID: number = Number(env.VITE_CHAIN_ID ?? 20261121);
export const SIWE_DOMAIN: string = env.VITE_SIWE_DOMAIN ?? "zyrcle.deviego.xyz";
export const REPO_URL = "https://github.com/diegowritescode/zyrcle";
