export const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB
export const ALLOWED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg', 'svg'] as const;
export const ACCEPT_ATTR = '.pdf,.png,.jpg,.jpeg,.svg';

function extensionOf(filename: string): string {
  const parts = filename.toLowerCase().split('.');
  return parts.length > 1 ? parts[parts.length - 1] : '';
}

/** Returns an error message if the file is invalid, otherwise null. */
export function validateFloorPlanFile(file: File): string | null {
  const ext = extensionOf(file.name);
  if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(ext)) {
    return 'Unsupported file type.';
  }
  if (file.size > MAX_FILE_SIZE) {
    return 'File size exceeds the 25 MB limit.';
  }
  return null;
}
