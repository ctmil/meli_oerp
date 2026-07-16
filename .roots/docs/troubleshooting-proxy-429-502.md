# Troubleshooting — Rate-limit ML (429), proxy de rescate, y 403/502

> Cómo diagnosticar problemas de conectividad ML: 429 (rate-limit), 403 (PolicyAgent), 502 (Bad Gateway
> del proxy). Basado en el caso RPM Motos (#532), 2026-07-16. Aplica a cualquier cliente que use el
> **proxy de rescate** (`res.company.mercadolibre_http_proxy`).

## El proxy de rescate — qué es
Campo `res.company.mercadolibre_http_proxy` (Settings → "Host API ML (rescate)"). Si está seteado,
`meli.util.get_new_instance` rutea las llamadas API+OAuth por un **reverse proxy externo** en vez de
`api.mercadolibre.com`, para **cambiar la IP de salida** cuando ML rate-limitea la IP del server.
- Deploy de referencia: **`proxy.moldeointeractive.com`** (server `moldeomint`, IP `45.33.103.179` =
  Linode US/Atlanta). nginx reverse-proxy → `https://api.mercadolibre.com` con `Host api.mercadolibre.com`.
  Config: `/etc/nginx/sites-available/proxy.moldeointeractive.com.conf`.

## Los 3 síntomas y qué significan (NO son lo mismo)
| Código | Qué es | Recuperable |
|---|---|---|
| **429** | Rate-limit: demasiadas requests desde la IP | **Sí** — con pacing/backoff (retry) |
| **403 PolicyAgent** (`PA_UNAUTHORIZED_RESULT_FROM_POLICIES`) | ML rechaza el request | Depende — ver abajo |
| **502 Bad Gateway** (nginx) | El proxy no obtuvo respuesta válida del upstream (ML) | Intermitente — retry |

### El 403 PolicyAgent NO es (necesariamente) un bloqueo de IP
**Gotcha clave (caso RPM):** ML devuelve **403 PolicyAgent** a requests **NO autenticados** desde IPs de
datacenter (probar `GET /sites/MLA` sin token da 403 desde una IP Linode/AWS). PERO las requests
**autenticadas (con `Authorization: Bearer <access_token>`) devuelven 200 normalmente**. → **un 403 en una
prueba sin token NO prueba que la IP esté bloqueada.** Los clientes Odoo en servers US funcionan porque su
tráfico real va autenticado. Siempre diagnosticar con token.

### El 502 = ML resetea ALGUNAS conexiones (throttling a nivel de conexión)
Intermitente y de baja frecuencia. En el error.log de nginx se ve como:
- `upstream prematurely closed connection while reading response header from upstream`
- `peer closed connection in SSL handshake (104: Connection reset by peer) while SSL handshaking to upstream`
Es el mismo rate-limit del 429 pero manifestado como **reset de conexión** → nginx lo reporta 502. La
mayoría de las requests pasan (200); sólo algunas se cortan.

## Cómo diagnosticar (desde el server del proxy, ej. `ssh moldeomint`)
```bash
TOK='APP_USR-...-<sellerid>'          # access_token vigente del cliente
# 1) autenticado DIRECTO a ML (aisla si la IP sirve tráfico autenticado)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOK" https://api.mercadolibre.com/users/me   # esperar 200
# 2) autenticado VIA PROXY (aisla si el proxy reenvía bien)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOK" https://proxy.moldeointeractive.com/users/me  # esperar 200
# 3) IP de salida (la que ve ML)
curl -s https://api.ipify.org
# 4) frecuencia de 502/reset en el log
sudo grep -iE "upstream|SSL handshak|reset|502" /var/log/nginx/error.log | tail
```
- 200 autenticado (directo y proxy) = **el proxy funciona**, no apagarlo.
- 403 sólo en pruebas SIN token = normal (datacenter), NO es bloqueo.
- 502 esporádico = throttling; ver "Mejoras".

## Mejoras para el 502 intermitente (pendientes)
1. **Retry en el conector ante 502/504:** agregarlos al `status_forcelist` del retry (overlay de rate-limit
   estilo Franco / `meli_http`) → recupera solo, no aparece como error en el chatter del pedido.
2. **Keepalive al upstream en nginx:** hoy cada request abre un SSL handshake nuevo (sin `upstream{}` +
   `keepalive`) → más handshakes = más chances de reset. Agregar keepalive reduce los resets.
3. **Doble slash** en la URL del proxy (`//users`, `//orders`) — ML lo tolera; limpiar por prolijidad.

## ⚠️ SEGURIDAD — token en los logs
El proxy pasa el `access_token` en la **query string** (`?access_token=...`), así que **queda logueado en
texto plano** en el access/error.log de nginx (se ve en el caso RPM). Mover a header `Authorization` o
filtrar/anonimizar el logging de nginx. Rotar tokens si el log se compartió.

## Relacionado: no pegarle a ML en el form load
La lentitud "al entrar a la cuenta MeLi" fue mayormente `get_connector_state` llamando `get_new_instance()`
(round-trip a ML) en un campo computado que corre en cada lectura — **peor con el 429** en la cuenta sin
proxy. Ver `meli_oerp_multiple/.roots/debug/fixes-log.md` (16 jul 2026). Regla: computar estado/contadores
sin API ni `len(o2m)` en el form.
