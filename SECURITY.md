# Seguridad — meli_oerp

## Cómo reportar una vulnerabilidad
Escribinos por los canales de contacto de Moldeo Interactive (https://www.moldeointeractive.com) con el detalle y, si podés, los pasos para
reproducirla. No abras un issue público. Confirmamos la recepción, la corregimos en todas las
versiones mantenidas y te avisamos cuando el arreglo está publicado.

## Avisos de seguridad

### 2026-10 — ruta pública `/download/saveas` eliminada
- **Qué:** la ruta HTTP heredada `/download/saveas` era accesible sin iniciar sesión. Ningún módulo
  la usaba. Se eliminó.
- **Corregido en:** 19.0.26.206 · 16.0/17.0/18.0 26.207 · 15.0.26.13 · 14.0.26.13 · 13.0.26.170
  (y en todos los builds posteriores).
- **Qué hacer:** actualizar `meli_oerp` a una de esas versiones o posterior.
- **Crédito:** reportado de forma responsable por **kta1kri**. ¡Gracias!
