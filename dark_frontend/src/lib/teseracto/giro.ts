/**
 * El ángulo que lleva rodado el teseracto del núcleo. Vive fuera del
 * componente porque su ciclo de vida no lo controla el input (ver el comentario
 * en TesseractCore), y aquí y no allí para que la ignición del arranque pueda
 * dejar la pose en la que terminó: el teseracto real sigue desde ella.
 */
export const giroAcumulado = { plano: 0, profundidad: 0 };
