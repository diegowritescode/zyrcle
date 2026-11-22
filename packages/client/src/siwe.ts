/**
 * Sign-In with Ethereum (EIP-4361) message, byte for byte what the API expects
 * (apps/api/src/zyrcle_api/auth.py, build_siwe). Any difference fails verification.
 */
export interface SiweFields {
  domain: string;
  address: string;
  chainId: number;
  nonce: string;
  issuedAt: Date;
}

export function buildSiweMessage({ domain, address, chainId, nonce, issuedAt }: SiweFields): string {
  return [
    `${domain} wants you to sign in with your Ethereum account:`,
    address,
    "",
    "Sign in to Zyrcle.",
    "",
    `URI: https://${domain}`,
    "Version: 1",
    `Chain ID: ${chainId}`,
    `Nonce: ${nonce}`,
    `Issued At: ${issuedAt.toISOString()}`,
  ].join("\n");
}
