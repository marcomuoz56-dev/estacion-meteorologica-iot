# Estacion Meteorologica IoT

Sistema de monitoreo meteorologico en tiempo real que captura variables atmosfericas
(temperatura, presion, altitud y humedad) mediante un sensor BME280 conectado a una
placa ESP32, y las transmite hacia la nube para su almacenamiento, procesamiento y
visualizacion remota.

Proyecto desarrollado para la asignatura Advanced Computer Structures de Broward
International University, bajo la direccion del profesor Cristian Gabriel Zambrano Vega, Phd.

---

## Que hace este proyecto?

1. Un sensor BME280 mide las condiciones meteorologicas del entorno cada 2 segundos
2. La ESP32 empaqueta las lecturas en formato JSON y las envia al broker MQTT en la nube
3. Un bridge Python recibe esos mensajes y los almacena en una base de datos PostgreSQL
4. Un dashboard web muestra los datos en graficas interactivas en tiempo real
5. Un servidor MCP permite que cualquier modelo de lenguaje (IA) consulte los datos del sensor

---

## Stack tecnologico

| Capa | Tecnologia | Funcion |
|------|-----------|---------|
| Sensor | BME280 | Medir temperatura, presion, altitud y humedad |
| Microcontrolador | ESP32 | Leer sensor, conectar WiFi, publicar MQTT |
| Comunicacion | HiveMQ Cloud (MQTT + TLS) | Transportar datos del sensor a la nube |
| Procesamiento | Python (paho-mqtt + httpx) | Recibir MQTT e insertar en base de datos |
| Base de datos | Supabase (PostgreSQL) | Almacenar lecturas con timestamp |
| Visualizacion | Firebase Hosting (Chart.js) | Dashboard web con graficas en tiempo real |
| Inteligencia Artificial | FastMCP | Exponer datos del sensor a modelos de lenguaje |
| MCP server | Horizon | Hacer accesible el servidor MCP desde internet |

---

## Arquitectura del sistema

El flujo de datos sigue este recorrido:

BME280 --I2C--> ESP32 --MQTT/TLS--> HiveMQ Cloud --MQTT--> Python Bridge --HTTP POST--> Supabase

Desde Supabase los datos se consumen en dos direcciones:
- El dashboard en Firebase consulta la API REST de Supabase cada 5 segundos
- El servidor MCP consulta Supabase cuando un LLM solicita informacion del sensor

---

## Instalacion paso a paso

### Paso 1: Crear la base de datos en Supabase

Supabase es una plataforma cloud que proporciona una base de datos PostgreSQL con APIs
REST automaticas. Se usa como almacen principal de las lecturas del sensor.

1. Crear cuenta gratuita en https://supabase.com
2. Crear un nuevo proyecto (anotar la URL y las API keys: anon y service_role)
3. Ir a SQL Editor y ejecutar el contenido del archivo `sql/schema.sql`

Esto creara la tabla `sensor_data` con las columnas necesarias y habilitara las politicas
de seguridad RLS (Row Level Security) que permiten lectura publica pero restringen la
escritura solo al service_role.

#### Que es RLS?
Row Level Security es un mecanismo de PostgreSQL que controla quien puede leer o escribir
en una tabla. En este proyecto se configuran dos politicas:
- **Lectura publica**: cualquier cliente con la anon key puede consultar datos (el dashboard)
- **Escritura restringida**: solo el Python Bridge con la service_role key puede insertar datos

---

### Paso 2: Configurar el broker MQTT en HiveMQ Cloud

HiveMQ Cloud es un broker MQTT administrado en la nube. MQTT es un protocolo ligero de
mensajeria disenado para dispositivos IoT con recursos limitados.

1. Crear cuenta gratuita en https://www.hivemq.com/cloud/
2. Crear un cluster (el plan Serverless es gratuito)
3. Crear credenciales de acceso (usuario y contrasena)
4. Anotar el host del cluster (formato: xxxx.s1.eu.hivemq.cloud) y el puerto (8883)

#### Por que MQTT y no HTTP POST directo?
MQTT desacopla el emisor (ESP32) del receptor (Python Bridge). El ESP32 solo publica
mensajes en un topico, sin saber quien los consume. Esto permite agregar multiples
suscriptores en el futuro sin modificar el firmware del dispositivo. Ademas, MQTT mantiene
conexiones persistentes con menor overhead que HTTP, lo cual es ideal para dispositivos
con recursos limitados.

---

### Paso 3: Programar la ESP32

La ESP32 es el dispositivo edge del sistema. Se encarga de leer el sensor BME280 por I2C,
serializar las lecturas en JSON y publicarlas en el broker MQTT cada 2 segundos.

#### Conexion fisica ESP32 - BME280

| ESP32 | BME280 | Funcion |
|-------|--------|---------|
| 3.3V | VCC | Alimentacion |
| GND | GND | Tierra |
| GPIO 21 | SDA | Datos I2C |
| GPIO 22 | SCL | Reloj I2C |

#### Configuracion del firmware

1. Abrir Arduino IDE
2. Instalar el core de ESP32: Archivo -> Preferencias -> URLs adicionales:
   `https://dl.espressif.com/dl/package_esp32_index.json`
3. Instalar librerias desde el Library Manager:
   - Adafruit BME280
   - Adafruit Unified Sensor
   - PubSubClient
   - ArduinoJson
4. Copiar `esp32/config.h.example` como `esp32/config.h`
5. Editar `config.h` con las credenciales reales de WiFi y HiveMQ
6. Abrir `esp32/estacion.ino` y cargarlo en la placa

#### Que hace el firmware?
- Se conecta a la red WiFi configurada
- Establece conexion TLS con el broker HiveMQ en el puerto 8883
- Lee temperatura, presion, altitud y humedad del sensor BME280
- Empaqueta los valores en un JSON: {"temperatura":22.5,"presion":752.3,"altitud":2445,"humedad":47.0}
- Publica el JSON en el topico `sensor/bmp280`
- Repite cada 2 segundos
- Se reconecta automaticamente si pierde WiFi o MQTT

---

### Paso 4: Ejecutar el Python Bridge

El bridge es el componente que conecta el broker MQTT con la base de datos Supabase.
Ademas, integra un servidor MCP que permite a modelos de lenguaje consultar los datos.

1. Copiar `bridge/.env.example` como `bridge/.env`
2. Editar `.env` con las credenciales reales:
   - SUPABASE_URL: la URL de tu proyecto Supabase
   - SUPABASE_KEY: la anon key (para lecturas)
   - SUPABASE_SERVICE_KEY: la service_role key (para escritura, bypasea RLS)
   - MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS: credenciales de HiveMQ
3. Instalar dependencias:
   `pip install paho-mqtt httpx fastmcp python-dotenv`
4. Ejecutar:
   `python bridge/bridgefinal.py`

#### Que hace el bridge?
El bridge ejecuta dos procesos en paralelo usando hilos (threading):
- **Hilo MQTT**: se suscribe al topico `sensor/bmp280`, recibe cada mensaje del ESP32
  y lo inserta en Supabase mediante HTTP POST con la service_role key
- **Hilo MCP**: expone un servidor en `http://localhost:8001/sse` con 6 herramientas
  de consulta y 2 prompts para generacion de dashboards

#### Herramientas MCP disponibles
| Herramienta | Descripcion |
|------------|-------------|
| obtener_ultima_lectura | Retorna el dato mas reciente del sensor |
| obtener_ultimas_lecturas | Historial de las ultimas N lecturas |
| obtener_datos_grafico | Datos en orden cronologico para graficas |
| obtener_resumen_estacion | Promedios, maximos y minimos estadisticos |
| detectar_alertas | Detecta condiciones fuera de rango normal |
| datos_para_dashboard | Paquete completo para construir dashboards |

---

### Paso 5: Desplegar el dashboard en Firebase Hosting

Firebase Hosting permite publicar el dashboard web de forma gratuita con HTTPS automatico
y CDN global.

1. Ir a https://console.firebase.google.com
2. Crear un nuevo proyecto (o usar uno existente)
3. Abrir Google Cloud Shell desde la consola de Firebase
4. Ejecutar los siguientes comandos:

`npm install -g firebase-tools`
`firebase login`
`firebase init hosting`
   - Seleccionar el proyecto creado
   - Directorio publico: `public`
   - No configurar como single-page app
   - No configurar builds automaticos con GitHub

5. Copiar el contenido de `firebase/public/index.html` en `public/index.html`
6. Desplegar:
   `firebase deploy`

#### Que hace el dashboard?
- Consulta la API REST de Supabase cada 5 segundos usando la anon key
- Muestra 4 metricas principales con iconos: temperatura, presion, altitud y humedad
- Presenta una grafica interactiva donde se puede alternar entre las 4 variables
- Calcula y muestra promedios por hora agrupando registros por timestamp
- Indica el estado de conexion: "En vivo" si hay datos recientes, o "Sin datos hace X min"
- Incluye seccion de integracion con IA mostrando la URL del servicio MCP

#### URL del dashboard
https://medidor-metereologico.web.app

---
| Hosting MCP (producción) | Horizon | Exponer el servidor MCP de forma permanente con URL pública estable |
---
### Paso 6: Desplegar el servidor MCP en Horizon

El servidor MCP (`server.py`) se despliega de forma permanente en Horizon para
contar con una URL pública estable, sin depender de mantener una máquina local
encendida.

1. Crear cuenta en Horizon y conectar el repositorio
2. Horizon detecta automáticamente el `Procfile` (`web: python bridgefinal.py`)
   y el `requirements.txt`
3. Configurar las variables de entorno (las mismas del archivo `.env`):
   SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY, MQTT_HOST, MQTT_PORT,
   MQTT_USER, MQTT_PASS
4. Desplegar — Horizon asigna una URL pública permanente

> **Nota histórica:** durante la fase de desarrollo, el servidor MCP se expuso
> temporalmente con [ngrok](https://ngrok.com), una herramienta que genera
> túneles HTTP hacia `localhost`. Esto permitió validar rápidamente la
> integración con LLMs externos, pero tenía limitaciones (URL cambiante en
> cada reinicio, un solo túnel activo en el plan gratuito). El despliegue en
> Horizon reemplaza ese paso para producción.

#### URL del servidor MCP

https://estacionmetereologica.fastmcp.app/mcp
---

### Paso 7: Conectar un LLM al servicio MCP

Una vez que el servidor MCP esta expuesto con ngrok, cualquier cliente compatible con
el protocolo MCP puede conectarse y consultar los datos del sensor.

#### Desde Claude.ai (metodo mas sencillo)
1. Abrir https://claude.ai
2. Ir a Personalizar (icono de engranaje) -> Conectores
3. Click en Agregar conector personalizado
4. Nombre: `estacion-meteorologica`
5. URL del servidor MCP remoto: pegar la URL generada por Horizon
   Ejemplo: `https://estacionmetereologica.fastmcp.app/mcp`
6. Dejar OAuth vacio
7. Click en Agregar
8. En cualquier chat, preguntar:
   - Cual es la temperatura actual?
   - Dame un resumen de las ultimas 50 lecturas
   - Hay alguna alerta meteorologica?
   - Genera un dashboard con los datos del sensor

Claude consultara automaticamente el servidor MCP, ejecutara las herramientas
correspondientes y respondera con datos reales del sensor en tiempo real.

---

## Seguridad implementada

| Mecanismo | Descripcion |
|-----------|-------------|
| TLS (puerto 8883) | Comunicacion cifrada entre ESP32 y HiveMQ |
| .env | Credenciales del bridge separadas del codigo fuente |
| config.h | Credenciales del ESP32 separadas del firmware |
| .gitignore | Impide que .env y config.h se suban al repositorio |
| RLS (Supabase) | Politicas de acceso diferenciadas: lectura publica, escritura restringida |
| service_role key | Solo el bridge puede insertar datos, no el dashboard ni clientes externos |

---

## Estructura del repositorio

estacion-meteorologica-iot/
- .gitignore (archivos excluidos del repositorio)
- README.md (este archivo)
- esp32/
  - estacion.ino (firmware de la ESP32)
  - config.h.example (plantilla de credenciales)
- bridge/
  - bridgefinal.py (bridge MQTT + MCP)
  - .env.example (plantilla de variables de entorno)
- firebase/
  - public/
    - index.html (dashboard web)
- sql/
  - schema.sql (creacion de tabla y politicas RLS)
- Procfile (comando de arranque para Horizon: web: python bridgefinal.py)
- requirements.txt (dependencias Python)
- server.py (punto de entrada del servidor MCP en producción)

---

## Dashboard
https://medidor-metereologico.web.app

## Autor
Marco Antonio Munoz Ramirez - Broward International University
