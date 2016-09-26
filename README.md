meli_oerp
=========

Módulo para sincronizar MercadoLibre con Odoo 8/9.

Para que funcione correctamente se debe tener instalado Odoo 8 o 9, en modo HTTPS (443).

Ver http://applications.mercadolibre.com.ar para obtener el client_id (app_id), y el secret key, para obtener el owner_id (vendor id), simplemente se hace un curl -X GET https://api.mercadolibre.com/applications/{app_id} , que devuelve la info de la app y del owner.

Ver http://developers.mercadolibre.com.ar para ver la API.

Ver los códigos de categoría aquí (MLA: Argentina, MLB: Brasil) :  https://api.mercadolibre.com/sites/MLA/categories .

Modo de uso:
1. Instalar el módulo
2. Para ver la pestaña de MercadoLibre en los productos, debe habilitar las "Variantes de Productos", usando el modo de administrador y cambiando la configuración en Sales>Settings (odoo 9) o en Settings (odoo 8).
2. Editar los datos de la empresa [EDIT COMPANY DATA] completando la pestaña de mercado libre con los datos correspondientes. Revisar la API de mercadolibre.com.ar. Utilizar como redirect_uri el valor de https://mi.servidor.com/meli_login
3. Modificar el meli_oerp_config.py y editar el parámetro REDIRECT_URI=https://mi.servidor.com/meli_login
4. Loguearse yendo a esa dirección https://mi.servidor.com/meli_login
5. Si todo va bien, debería poder completar y postear
  
<h2>Authors</h2>
<h4>Original Author and Development Lead</h4>
<h5>Fabricio Costa (fabricio.costa(at)moldeointeractive.com.ar)</h5>
