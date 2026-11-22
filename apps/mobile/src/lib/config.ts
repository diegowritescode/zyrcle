/** Build-time configuration (EXPO_PUBLIC_*), defaulting to the public testnet deployment. */
export const API_URL = process.env.EXPO_PUBLIC_API_URL || "https://zyrcle-backend.deviego.xyz";
export const RPC_URL =
  process.env.EXPO_PUBLIC_RPC_URL ||
  "https://rpc.zyrcle.deviego.xyz/ext/bc/hXdnq6H8N9gH3o5cpKWGMzspesNyogKjuDwZESQhQNNtM5jN8/rpc";
export const CHAIN_ID = Number(process.env.EXPO_PUBLIC_CHAIN_ID || 20261121);
/** The domain residents sign in to (SIWE): the same as the web app's, checked by the API. */
export const SIWE_DOMAIN = process.env.EXPO_PUBLIC_SIWE_DOMAIN || "zyrcle.deviego.xyz";
/** AccountFactory on ZyrcleChain (docs/adr/0010). Lets the app check, on its own, that the account
 * the API names really belongs to this phone's key before moving coins there. Empty: no check, no
 * move. Defaults to the testnet deployment (infra/l1/fuji.env). */
export const ACCOUNT_FACTORY = process.env.EXPO_PUBLIC_ACCOUNT_FACTORY || "0x0bE806Ca77340aA50AF6586CDC2FE2561668DaEA";
export const WEB_URL = process.env.EXPO_PUBLIC_WEB_URL || "https://zyrcle.deviego.xyz";
export const REPO_URL = "https://github.com/diegowritescode/zyrcle";
