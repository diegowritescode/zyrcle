import type { DownloadedFile } from "@zyrcle/client";

/** Save a file the API sent (an export, docs/adr/0045) through the browser's own download. */
export function saveFile(file: DownloadedFile): void {
    const url = URL.createObjectURL(new Blob([file.bytes as BlobPart], { type: file.type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = file.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
