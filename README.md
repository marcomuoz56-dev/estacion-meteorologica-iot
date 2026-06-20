# Estacion Meteorologica IoT

Sistema de monitoreo meteorologico en tiempo real con ESP32 + BME280.

## Stack
- **Hardware**: ESP32 + BME280 (I2C)
- **Comunicacion**: MQTT TLS (HiveMQ Cloud)
- **Bridge**: Python (paho-mqtt + httpx + FastMCP)
- **Base de datos**: Supabase (PostgreSQL)
- **Dashboard**: Firebase Hosting (Chart.js)
- **IA**: Servidor MCP para integracion con LLMs

## Arquitectura
BME280 -> ESP32 -> MQTT/TLS -> HiveMQ Cloud -> Python Bridge -> Supabase -> Firebase Hosting (Dashboard) + MCP Server

## Instalacion

### 1. Base de datos
Ejecutar sql/schema.sql en el SQL Editor de Supabase.

### 2. ESP32
- Copiar esp32/config.h.example como esp32/config.h
- Llenar credenciales WiFi y MQTT
- Cargar esp32/estacion.ino con Arduino IDE

### 3. Bridge
cd bridge
cp .env.example .env
pip install paho-mqtt httpx fastmcp python-dotenv
python bridgefinal.py

### 4. Dashboard
cd firebase
firebase init hosting
firebase deploy

## Dashboard
https://medidor-metereologico.web.app

## Autor
Marco Antonio Munoz Ramirez - Broward International University
