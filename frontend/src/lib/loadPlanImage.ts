import * as pdfjsLib from 'pdfjs-dist';
import PdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker';

// Vite `?worker` import spins up the worker reliably (avoids MIME/URL issues).
pdfjsLib.GlobalWorkerOptions.workerPort = new PdfjsWorker();

export interface PlanImage {
  image: HTMLImageElement;
  width: number;
  height: number;
}

function loadHtmlImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Failed to load image'));
    img.src = src;
  });
}

/**
 * Loads a floor plan into an HTMLImageElement usable as a Konva image.
 * PDFs are rasterized (page 1) via pdf.js; images load directly.
 */
export async function loadPlanImage(url: string, isPdf: boolean): Promise<PlanImage> {
  if (!isPdf) {
    const image = await loadHtmlImage(url);
    const width = image.naturalWidth || 1000;
    const height = image.naturalHeight || 750;
    return { image, width, height };
  }

  const pdf = await pdfjsLib.getDocument(url).promise;
  const page = await pdf.getPage(1);
  const viewport = page.getViewport({ scale: 2 });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D context unavailable');
  await page.render({ canvasContext: context, viewport }).promise;
  const image = await loadHtmlImage(canvas.toDataURL('image/png'));
  return { image, width: canvas.width, height: canvas.height };
}
