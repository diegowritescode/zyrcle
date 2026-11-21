import type { EIP1193Provider, Web3APISpec } from "web3";

// Injected wallet (MetaMask, Core). Only present when the user has a wallet extension.
type InjectedProvider = EIP1193Provider<Web3APISpec> & {
  on(event: "accountsChanged" | "chainChanged", handler: (...args: unknown[]) => void): void;
};

declare global {
  interface Window {
    ethereum?: InjectedProvider;
  }
}

export {};
