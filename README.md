meli_oerp
=========

Módulo para sincronizar MercadoLibre con Odoo 13.

Para que funcione correctamente se debe tener instalado Odoo 13 Community o Enterprise, en modo HTTPS (443).

Ver http://applications.mercadolibre.com.ar para obtener el client_id (app_id), y el secret key, para obtener el owner_id (vendor id), simplemente se hace un curl -X GET https://api.mercadolibre.com/applications/{app_id} , que devuelve la info de la app y del owner.

!!UPDATE: El applications/app_id ya no devuelve el owner_id (aunque la documentación de la api siga diciendo que lo hace)
Para obtener su id, si está ya logueado debe completar su nombre de usuario ML en este URL:

Para Argentina: https://api.mercadolibre.com/sites/MLA/search?nickname=ESCRIBE_AQUI_TU_NICK_NAME

Para Chile: https://api.mercadolibre.com/sites/MLC/search?nickname=ESCRIBE_AQUI_TU_NICK_NAME

Para México: https://api.mercadolibre.com/sites/MLM/search?nickname=ESCRIBE_AQUI_TU_NICK_NAME

Para Costa RIca: https://api.mercadolibre.com/sites/MCR/search?nickname=ESCRIBE_AQUI_TU_NICK_NAME

[...]

Ver http://developers.mercadolibre.com.ar para ver la API.

Ver los códigos de categoría aquí (MLA: Argentina, MLB: Brasil) :  https://api.mercadolibre.com/sites/MLA/categories .
Para Costa Rica: https://api.mercadolibre.com/sites/MCR/categories

<h2>Instrucciones básicas de configuración:</h2>

<h4>1. Instalar el módulo</h4>
Descargar desde github utilizando siempre el branch correspondiente:
git clone https://github.com/ctmil/meli_oerp -b 12.0
git clone https://github.com/ctmil/meli_oerp -b 11.0
git clone https://github.com/ctmil/meli_oerp -b 10.0
Siempre mantener el nombre del módulo como "meli_oerp" en su carpeta de addons.

<h4>2. Habilitar la opción de variantes.</h4>
Para ver los productos (la variante es dónde reside el meli id de cada producto) y sus urls respectivos, debe habilitar las "Variantes de Productos", usando el modo de administrador y cambiando la configuración de variantes.

<h4>3. Editar los datos de la empresa</h4>
Completando la pestaña de mercado libre con los datos correspondientes:
<b>Client ID</b>
<b>Secret Key</b>
<b>Redirect Uri</b>
<b>vendor Id</b>
Utilizar como <b>redirect_uri</b> el valor de: https://[dominio del server]/meli_login

<h4>4. Loguearse una vez completados los pasos de configuración,</h4> Utilizando el botón: "Iniciar Sesión"

<h4>4. Pueden ver el video en el link siguiente</h4>
<a href="https://www.moldeointeractive.com.ar/shop/product/instalacion-modulo-odoo-mercadolibre-15">Video + Info</a>


<h2>Authors</h2>
<h4>Original Author and Development Lead</h4>
<h5>Fabricio Costa (fabricio.costa(at)moldeointeractive.com.ar)</h5>
