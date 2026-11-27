import type { DownloadedFile } from "@zyrcle/client";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";

/**
 * Give the person a file the API sent (the merchant's export, docs/adr/0045): on the phone, the
 * share sheet, so it goes to WhatsApp, Drive, an email or the phone's files; in a browser, a plain
 * download. The phone's copy sits in the app's cache, which Android empties when it needs room.
 */
export async function handOver(file: DownloadedFile): Promise<void> {
  if (Platform.OS === "web") {
    const url = URL.createObjectURL(new Blob([file.bytes as BlobPart], { type: file.type }));
    const link = globalThis.document.createElement("a");
    link.href = url;
    link.download = file.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    return;
  }
  const copy = new File(Paths.cache, file.name);
  if (copy.exists) copy.delete();
  copy.create();
  await copy.write(file.bytes);
  await Sharing.shareAsync(copy.uri, { mimeType: file.type.split(";")[0], dialogTitle: file.name });
}
