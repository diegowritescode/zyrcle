/** A photo from the phone or the computer, as a JPEG small enough to send and to read: the long
 * side at most `maxSide` pixels. HEIC photos open only where the browser can decode them. */
export async function photoToJpeg(file: File, maxSide = 1600): Promise<{ base64: string; previewUrl: string }> {
    let bitmap: ImageBitmap;
    try {
        bitmap = await createImageBitmap(file);
    } catch {
        throw new Error("No pudimos abrir esa foto. Usa una foto JPG o PNG.");
    }
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) =>
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("No pudimos preparar la foto."))), "image/jpeg", 0.85),
    );
    const base64 = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
        reader.readAsDataURL(blob);
    });
    return { base64, previewUrl: URL.createObjectURL(blob) };
}
