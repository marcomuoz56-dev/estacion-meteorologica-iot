// ─── Librerías ───────────────────────────────────────────────────────────────
#include <Wire.h>              // Comunicación I2C con el sensor
#include <Adafruit_BME280.h>   // Driver del sensor BME280
#include <Adafruit_Sensor.h>   // Dependencia base de Adafruit
#include <WiFi.h>              // Conexión WiFi del ESP32
#include <WiFiClientSecure.h>  // Cliente WiFi con soporte TLS
#include <PubSubClient.h>      // Cliente MQTT
#include <ArduinoJson.h>       // Serialización de datos a JSON
#include "config.h"            // Credenciales WiFi y MQTT (excluido del repo)

// ─── Instancias globales ─────────────────────────────────────────────────────
Adafruit_BME280 bme;           // Sensor BME280 por I2C
WiFiClientSecure espClient;    // Cliente WiFi con TLS para HiveMQ puerto 8883
PubSubClient client(espClient);// Cliente MQTT sobre la conexión segura

// ─── Conexión WiFi ───────────────────────────────────────────────────────────
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASS);  // Inicia conexión con credenciales del config.h
  Serial.print("Conectando WiFi");
  while (WiFi.status() != WL_CONNECTED) { // Espera hasta tener IP
    delay(500);
    Serial.print(".");
  }
  Serial.println(" conectado");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());     // Imprime IP asignada por el router
}

// ─── Conexión MQTT ───────────────────────────────────────────────────────────
void connectMQTT() {
  espClient.setInsecure();            // TLS sin validar certificado (modo desarrollo)
  client.setServer(MQTT_HOST, MQTT_PORT); // Apunta al broker HiveMQ Cloud puerto 8883
  while (!client.connected()) {
    Serial.println("Conectando MQTT...");
    if (client.connect("ESP32_BME280", MQTT_USER, MQTT_PASS)) { // Autenticación con credenciales
      Serial.println("MQTT conectado");
    } else {
      Serial.print("Error MQTT, estado: ");
      Serial.println(client.state()); // Código de error si falla la conexión
      delay(500);
    }
  }
}

// ─── Setup — ejecuta una sola vez al encender ────────────────────────────────
void setup() {
  Serial.begin(115200);               // Inicia monitor serial a 115200 baudios

  if (!bme.begin(0x76)) {             // Inicializa BME280 en dirección I2C 0x76
    Serial.println("BME280 no encontrado");
    while (1) delay(10);              // Detiene ejecución si no encuentra el sensor
  }
  Serial.println("BME280 OK");

  // Configura el modo de muestreo del sensor
  bme.setSampling(Adafruit_BME280::MODE_NORMAL,      // Muestreo continuo
                  Adafruit_BME280::SAMPLING_X2,       // Temperatura: 2 muestras promediadas
                  Adafruit_BME280::SAMPLING_X16,      // Presión: 16 muestras promediadas
                  Adafruit_BME280::SAMPLING_X1,       // Humedad: 1 muestra
                  Adafruit_BME280::FILTER_X16,        // Filtro IIR para reducir ruido
                  Adafruit_BME280::STANDBY_MS_500);   // 500ms entre mediciones

  connectWiFi();   // Conecta a la red WiFi
  connectMQTT();   // Conecta al broker MQTT
}

// ─── Loop — se repite indefinidamente ────────────────────────────────────────
void loop() {
  if (!client.connected()) connectMQTT(); // Reconecta si se pierde la conexión MQTT
  client.loop();                          // Mantiene viva la conexión MQTT

  // ─── Lectura del sensor ───────────────────────────────────────────────────
  float temperatura = bme.readTemperature();          // °C
  float presion     = bme.readPressure() / 100.0F;   // Pa → hPa
  float altitud     = bme.readAltitude(1013.25);      // Metros sobre nivel del mar
  float humedad     = bme.readHumidity();             // Porcentaje de humedad relativa

  // ─── Diagnóstico en monitor serial ───────────────────────────────────────
  Serial.println("---- Lectura BME280 ----");
  Serial.println(MQTT_TOPIC);
  Serial.print("Temperatura: "); Serial.print(temperatura); Serial.println(" *C");
  Serial.print("Presion:     "); Serial.print(presion);     Serial.println(" hPa");
  Serial.print("Altitud:     "); Serial.print(altitud);     Serial.println(" m");
  Serial.print("Humedad:     "); Serial.print(humedad);     Serial.println(" %");

  // ─── Serialización a JSON ─────────────────────────────────────────────────
  StaticJsonDocument<200> doc;       // Documento JSON de 200 bytes en stack
  doc["temperatura"] = temperatura;
  doc["presion"]     = presion;
  doc["altitud"]     = altitud;
  doc["humedad"]     = humedad;

  char payload[200];
  serializeJson(doc, payload);       // Convierte el documento a string JSON

  // ─── Publicación MQTT ─────────────────────────────────────────────────────
  // Envía el JSON al tópico definido en config.h → HiveMQ → Python Bridge → Supabase
  if (client.publish(MQTT_TOPIC, payload)) {
    Serial.println("Publicado OK");
  } else {
    Serial.println("Error al publicar");
  }

  Serial.println("------------------------");
  delay(2000);  // Espera 2 segundos antes de la siguiente lectura
}