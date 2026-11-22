/** Build-time configuration (Vite env), with the public testnet deployment as the default. */
const env = import.meta.env;

export const API_URL: string = env.VITE_API_URL || "http://127.0.0.1:8000";
export const RPC_URL: string =
  env.VITE_RPC_URL ||
  "https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc";
export const CHAIN_ID: number = Number(env.VITE_CHAIN_ID || 20261121);
/** The domain residents sign in to (SIWE). Must match the API's ZYRCLE_SIWE_DOMAIN. */
export const SIWE_DOMAIN: string = env.VITE_SIWE_DOMAIN || "zyrcle.deviego.xyz";
export const TREASURY_ADDRESS: string =
  env.VITE_TREASURY_ADDRESS || "0xB843946A42F2791B8b932F8c0205C9D277E351B1";
export const REPO_URL = "https://github.com/diegowritescode/zyrcle";
export const docUrl = (path: string) => `${REPO_URL}/blob/main/${path}`;
