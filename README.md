# Estación Meteorológica IoT

Sistema de monitoreo meteorológico en tiempo real que captura variables atmosféricas (temperatura, presión, altitud y humedad) mediante un sensor BME280 conectado a una placa ESP32, y las transmite hacia la nube para su almacenamiento, procesamiento y visualización remota.

Proyecto desarrollado para la asignatura Advanced Computer Structures de Broward International University, bajo la dirección del profesor Cristian Gabriel Zambrano Vega, PhD.

---

## ¿Qué hace este proyecto?

1. Un sensor BME280 mide las condiciones meteorológicas del entorno cada 2 segundos.
2. La ESP32 empaqueta las lecturas en formato JSON y las envía al broker MQTT en la nube.
3. Un bridge Python recibe esos mensajes y los almacena en una base de datos PostgreSQL.
4. Un dashboard web muestra los datos en gráficas interactivas en tiempo real.
5. Un servidor MCP permite que cualquier modelo de lenguaje (IA) consulte los datos del sensor.

---

## Stack tecnológico

| Capa                    | Tecnología                  | Función                                        |
| ----------------------- | --------------------------- | ---------------------------------------------- |
| Sensor                  | BME280                      | Medir temperatura, presión, altitud y humedad  |
| Microcontrolador        | ESP32                       | Leer sensor, conectar WiFi, publicar MQTT      |
| Comunicación            | HiveMQ Cloud (MQTT + TLS)   | Transportar datos del sensor a la nube         |
| Procesamiento           | Python (paho-mqtt + httpx)  | Recibir MQTT e insertar en base de datos       |
| Base de datos           | Supabase (PostgreSQL)       | Almacenar lecturas con timestamp               |
| Visualización           | Firebase Hosting (Chart.js) | Dashboard web con gráficas en tiempo real      |
| Inteligencia Artificial | FastMCP                     | Exponer datos del sensor a modelos de lenguaje |
| MCP Server              | Horizon                     | Hacer accesible el servidor MCP desde internet |

---

## Arquitectura del sistema

El flujo de datos sigue este recorrido:

BME280 --I2C--> ESP32 --MQTT/TLS--> HiveMQ Cloud --MQTT--> Python Bridge --HTTP POST--> Supabase

Desde Supabase, los datos se consumen en dos direcciones:

* El dashboard en Firebase consulta la API REST de Supabase cada 5 segundos.
* El servidor MCP consulta Supabase cuando un LLM solicita información del sensor.

---

## Instalación paso a paso

### Paso 1: Crear la base de datos en Supabase

Supabase es una plataforma cloud que proporciona una base de datos PostgreSQL con APIs REST automáticas. Se usa como almacén principal de las lecturas del sensor.

1. Crear una cuenta gratuita en [https://supabase.com](https://supabase.com).
2. Crear un nuevo proyecto (anotar la URL y las API keys: anon y service_role).
3. Ir a SQL Editor y ejecutar el contenido del archivo `sql/schema.sql`.

Esto creará la tabla `sensor_data` con las columnas necesarias y habilitará las políticas de seguridad RLS (Row Level Security), que permiten lectura pública, pero restringen la escritura solo al service_role.

#### ¿Qué es RLS?

Row Level Security es un mecanismo de PostgreSQL que controla quién puede leer o escribir en una tabla. En este proyecto se configuran dos políticas:

* **Lectura pública**: cualquier cliente con la anon key puede consultar datos (el dashboard).
* **Escritura restringida**: solo el Python Bridge con la service_role key puede insertar datos.

---

### Paso 2: Configurar el broker MQTT en HiveMQ Cloud

HiveMQ Cloud es un broker MQTT administrado en la nube. MQTT es un protocolo ligero de mensajería diseñado para dispositivos IoT con recursos limitados.

1. Crear una cuenta gratuita en [https://www.hivemq.com/cloud/](https://www.hivemq.com/cloud/).
2. Crear un clúster (el plan Serverless es gratuito).
3. Crear credenciales de acceso (usuario y contraseña).
4. Anotar el host del clúster (formato: xxxx.s1.eu.hivemq.cloud) y el puerto (8883).

#### ¿Por qué MQTT y no HTTP POST directo?

MQTT desacopla el emisor (ESP32) del receptor (Python Bridge). El ESP32 solo publica mensajes en un tópico, sin saber quién los consume. Esto permite agregar múltiples suscriptores en el futuro sin modificar el firmware del dispositivo. Además, MQTT mantiene conexiones persistentes con menor overhead que HTTP, lo cual es ideal para dispositivos con recursos limitados.

---

### Paso 3: Programar la ESP32

La ESP32 es el dispositivo edge del sistema. Se encarga de leer el sensor BME280 por I2C, serializar las lecturas en JSON y publicarlas en el broker MQTT cada 2 segundos.

#### Conexión física ESP32 - BME280

| ESP32   | BME280 | Función      |
| ------- | ------ | ------------ |
| 3.3V    | VCC    | Alimentación |
| GND     | GND    | Tierra       |
| GPIO 21 | SDA    | Datos I2C    |
| GPIO 22 | SCL    | Reloj I2C    |

#### Configuración del firmware

1. Abrir Arduino IDE.
2. Instalar el core de ESP32: Archivo -> Preferencias -> URLs adicionales:
   `https://dl.espressif.com/dl/package_esp32_index.json`
3. Instalar librerías desde el Library Manager:

   * Adafruit BME280
   * Adafruit Unified Sensor
   * PubSubClient
   * ArduinoJson
4. Copiar `esp32/config.h.example` como `esp32/config.h`.
5. Editar `config.h` con las credenciales reales de WiFi y HiveMQ.
6. Abrir `esp32/estacion.ino` y cargarlo en la placa.

#### ¿Qué hace el firmware?

* Se conecta a la red WiFi configurada.
* Establece conexión TLS con el broker HiveMQ en el puerto 8883.
* Lee temperatura, presión, altitud y humedad del sensor BME280.
* Empaqueta los valores en un JSON: `{"temperatura":22.5,"presion":752.3,"altitud":2445,"humedad":47.0}`.
* Publica el JSON en el tópico `sensor/bmp280`.
* Repite cada 2 segundos.
* Se reconecta automáticamente si pierde WiFi o MQTT.

---

### Paso 4: Ejecutar el Python Bridge

El bridge es el componente que conecta el broker MQTT con la base de datos Supabase. Además, integra un servidor MCP que permite a modelos de lenguaje consultar los datos.

1. Copiar `bridge/.env.example` como `bridge/.env`.
2. Editar `.env` con las credenciales reales:

   * SUPABASE_URL: la URL de tu proyecto Supabase.
   * SUPABASE_KEY: la anon key (para lecturas).
   * SUPABASE_SERVICE_KEY: la service_role key (para escritura, bypass de RLS).
   * MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS: credenciales de HiveMQ.
3. Instalar dependencias:
   `pip install paho-mqtt httpx fastmcp python-dotenv`
4. Ejecutar:
   `python bridge/bridgefinal.py`

#### ¿Qué hace el bridge?

El bridge ejecuta dos procesos en paralelo usando hilos (threading):

* **Hilo MQTT**: se suscribe al tópico `sensor/bmp280`, recibe cada mensaje del ESP32 y lo inserta en Supabase mediante HTTP POST con la service_role key.
* **Hilo MCP**: expone un servidor en `http://localhost:8001/sse` con 6 herramientas de consulta y 2 prompts para generación de dashboards.

#### Herramientas MCP disponibles

| Herramienta              | Descripción                                |
| ------------------------ | ------------------------------------------ |
| obtener_ultima_lectura   | Retorna el dato más reciente del sensor    |
| obtener_ultimas_lecturas | Historial de las últimas N lecturas        |
| obtener_datos_grafico    | Datos en orden cronológico para gráficas   |
| obtener_resumen_estacion | Promedios, máximos y mínimos estadísticos  |
| detectar_alertas         | Detecta condiciones fuera de rango normal  |
| datos_para_dashboard     | Paquete completo para construir dashboards |

---

### Paso 5: Desplegar el dashboard en Firebase Hosting

Firebase Hosting permite publicar el dashboard web de forma gratuita con HTTPS automático y CDN global.

1. Ir a [https://console.firebase.google.com](https://console.firebase.google.com).
2. Crear un nuevo proyecto (o usar uno existente).
3. Abrir Google Cloud Shell desde la consola de Firebase.
4. Ejecutar los siguientes comandos:

`npm install -g firebase-tools`

`firebase login`

`firebase init hosting`

* Seleccionar el proyecto creado.
* Directorio público: `public`.
* No configurar como single-page app.
* No configurar builds automáticos con GitHub.

5. Copiar el contenido de `firebase/public/index.html` en `public/index.html`.
6. Desplegar:

`firebase deploy`

#### ¿Qué hace el dashboard?

* Consulta la API REST de Supabase cada 5 segundos usando la anon key.
* Muestra 4 métricas principales con iconos: temperatura, presión, altitud y humedad.
* Presenta una gráfica interactiva donde se puede alternar entre las 4 variables.
* Calcula y muestra promedios por hora agrupando registros por timestamp.
* Indica el estado de conexión: "En vivo" si hay datos recientes, o "Sin datos hace X min".
* Incluye una sección de integración con IA mostrando la URL del servicio MCP.

#### URL del dashboard

[https://medidor-metereologico.web.app](https://medidor-metereologico.web.app)

---

| Hosting MCP (producción) | Horizon | Exponer el servidor MCP de forma permanente con URL pública estable |
| ------------------------ | ------- | ------------------------------------------------------------------- |

### Paso 6: Desplegar el servidor MCP en Horizon

El servidor MCP (`server.py`) se despliega de forma permanente en Horizon para contar con una URL pública estable, sin depender de mantener una máquina local encendida.

1. Crear una cuenta en Horizon y conectar el repositorio.
2. Horizon detecta automáticamente el `Procfile` (`web: python bridgefinal.py`) y el `requirements.txt`.
3. Configurar las variables de entorno (las mismas del archivo `.env`):
   SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS.
4. Desplegar. Horizon asigna una URL pública permanente.

> **Nota histórica:** Durante la fase de desarrollo, el servidor MCP se expuso temporalmente con ngrok, una herramienta que genera túneles HTTP hacia `localhost`. Esto permitió validar rápidamente la integración con LLMs externos, pero tenía limitaciones (URL cambiante en cada reinicio y un solo túnel activo en el plan gratuito). El despliegue en Horizon reemplaza ese paso para producción.

#### URL del servidor MCP

[https://estacionmetereologica.fastmcp.app/mcp](https://estacionmetereologica.fastmcp.app/mcp)

---

### Paso 7: Conectar un LLM al servicio MCP

Una vez que el servidor MCP está expuesto con Horizon, cualquier cliente compatible con el protocolo MCP puede conectarse y consultar los datos del sensor.

#### Desde Claude.ai (método más sencillo)

1. Abrir [https://claude.ai](https://claude.ai).
2. Ir a Personalizar (ícono de engranaje) -> Conectores.
3. Hacer clic en Agregar conector personalizado.
4. Nombre: `estacion-meteorologica`.
5. URL del servidor MCP remoto: pegar la URL generada por Horizon.
   Ejemplo: `https://estacionmetereologica.fastmcp.app/mcp`
6. Dejar OAuth vacío.
7. Hacer clic en Agregar.
8. En cualquier chat, preguntar:

   * ¿Cuál es la temperatura actual?
   * Dame un resumen de las últimas 50 lecturas.
   * ¿Hay alguna alerta meteorológica?
   * Genera un dashboard con los datos del sensor.

Claude consultará automáticamente el servidor MCP, ejecutará las herramientas correspondientes y responderá con datos reales del sensor en tiempo real.

---

## Seguridad implementada

| Mecanismo         | Descripción                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| TLS (puerto 8883) | Comunicación cifrada entre ESP32 y HiveMQ                                 |
| .env              | Credenciales del bridge separadas del código fuente                       |
| config.h          | Credenciales del ESP32 separadas del firmware                             |
| .gitignore        | Impide que .env y config.h se suban al repositorio                        |
| RLS (Supabase)    | Políticas de acceso diferenciadas: lectura pública, escritura restringida |
| service_role key  | Solo el bridge puede insertar datos, no el dashboard ni clientes externos |

---

## Estructura del repositorio

estacion-meteorologica-iot/

* .gitignore (archivos excluidos del repositorio)
* README.md (este archivo)
* esp32/

  * estacion.ino (firmware de la ESP32)
  * config.h.example (plantilla de credenciales)
* bridge/

  * bridgefinal.py (bridge MQTT + MCP)
  * .env.example (plantilla de variables de entorno)
* firebase/

  * public/

    * index.html (dashboard web)
* sql/

  * schema.sql (creación de tabla y políticas RLS)
* Procfile (comando de arranque para Horizon: `web: python bridgefinal.py`)
* requirements.txt (dependencias Python)
* server.py (punto de entrada del servidor MCP en producción)

---

## Dashboard

[https://medidor-metereologico.web.app](https://medidor-metereologico.web.app)

## Autor

Marco Antonio Muñoz Ramírez - Broward International University
