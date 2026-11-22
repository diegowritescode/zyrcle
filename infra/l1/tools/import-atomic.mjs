// Import AVAX sitting in P-Chain shared memory (exported from the C-Chain) into a P-Chain address.
//
// Avalanche CLI 1.9.7 issues the C-Chain ExportTx and then polls avax.getAtomicTxStatus, which
// AvalancheGo v1.15 removed; it errors out before issuing the P-Chain ImportTx and the funds stay
// in shared memory. This finishes the transfer.
//
// Usage: KEY_FILE=/path/to/key.pk node import-atomic.mjs <P-fuji1...> [--dry-run]
import { readFileSync } from "node:fs";
import { addTxSignatures, Context, pvm, utils } from "@avalabs/avalanchejs";

const uri = process.env.AVAX_URI ?? "https://api.avax-test.network";
const [address, flag] = process.argv.slice(2);
if (!address?.startsWith("P-")) throw new Error("usage: import-atomic.mjs <P-address> [--dry-run]");

const api = new pvm.PVMApi(uri);
const context = await Context.getContextFromURI(uri);
const { utxos } = await api.getUTXOs({ sourceChain: "C", addresses: [address] });
const total = utxos.reduce((sum, u) => sum + u.output.amount(), 0n);
console.log(`atomic UTXOs from C-Chain: ${utxos.length}, total ${Number(total) / 1e9} AVAX`);
if (utxos.length === 0 || flag === "--dry-run") process.exit(0);

const keyHex = readFileSync(process.env.KEY_FILE, "utf8").trim().replace(/^0x/, "");
const addressBytes = utils.bech32ToBytes(address);
const tx = pvm.e.newImportTx(
  {
    feeState: await api.getFeeState(),
    fromAddressesBytes: [addressBytes],
    sourceChainId: context.cBlockchainID,
    toAddressesBytes: [addressBytes],
    utxos,
  },
  context,
);
await addTxSignatures({ unsignedTx: tx, privateKeys: [utils.hexToBuffer(keyHex)] });
const { txID } = await api.issueSignedTx(tx.getSignedTx());
console.log(`ImportTx issued: ${txID}`);
