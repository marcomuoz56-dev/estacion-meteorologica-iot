import json
import httpx
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from fastmcp import FastMCP
from datetime import datetime
import os
import threading

# ─── Carga de variables de entorno desde el archivo .env ────────────────────
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")                 # anon key — solo lectura pública
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") # service_role — bypasea RLS para INSERT
MQTT_HOST    = os.getenv("MQTT_HOST")
MQTT_PORT    = int(os.getenv("MQTT_PORT"))
MQTT_USER    = os.getenv("MQTT_USER")
MQTT_PASS    = os.getenv("MQTT_PASS")
MQTT_TOPIC   = os.getenv("MQTT_TOPIC")

# ─── Headers diferenciados por rol — seguridad RLS ──────────────────────────
# WRITE: service_role para insertar datos del sensor (bypasea políticas RLS)
HEADERS_WRITE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}
# READ: anon key respeta políticas RLS de solo lectura
HEADERS_READ = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ─── Servidor MCP — expone herramientas a LLMs externos ─────────────────────
# FastMCP crea un servidor compatible con Model Context Protocol
# Cualquier cliente MCP (Claude Desktop, Gemini, etc.) puede consumir estas tools
mcp = FastMCP("estacion-meteorologica")

def _query(limit: int = 1, order: str = "desc"):
    """Helper interno — consulta Supabase con orden y límite parametrizados."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=*&order=created_at.{order}&limit={limit}",
        headers=HEADERS_READ
    )
    return res.json()

# ─── Tool 1: lectura más reciente ───────────────────────────────────────────
@mcp.tool()
def obtener_ultima_lectura() -> dict:
    """Obtiene la lectura más reciente de la estación meteorológica.
    Usar cuando el usuario pregunte por temperatura, humedad, presión o altitud actual."""
    data = _query(limit=1)
    if not data:
        return {"error": "No hay lecturas registradas"}
    return data[0]

# ─── Tool 2: histórico de N lecturas ────────────────────────────────────────
@mcp.tool()
def obtener_ultimas_lecturas(limite: int = 50) -> list:
    """Obtiene una lista de las últimas N lecturas registradas.
    Usar cuando se requiera histórico reciente o tabla de datos."""
    return _query(limit=limite)

# ─── Tool 3: datos en orden cronológico para gráficos ───────────────────────
@mcp.tool()
def obtener_datos_grafico(limite: int = 100) -> list:
    """Prepara datos para construir gráficos en orden cronológico ascendente.
    Usar cuando se necesite serie temporal o visualización histórica."""
    return _query(limit=limite, order="asc")

# ─── Tool 4: estadísticas agregadas ─────────────────────────────────────────
@mcp.tool()
def obtener_resumen_estacion(limite: int = 100) -> dict:
    """Calcula estadísticas (promedio, máximo, mínimo) de las últimas N lecturas.
    Usar cuando se soliciten promedios, máximos, mínimos o resumen general."""
    rows = _query(limit=limite)
    if not rows:
        return {"error": "Sin datos"}
    
    # Función interna para calcular stats de cualquier campo numérico
    def stats(field):
        vals = [r[field] for r in rows if r.get(field) is not None]
        return {
            "promedio": round(sum(vals) / len(vals), 2),
            "maximo":   round(max(vals), 2),
            "minimo":   round(min(vals), 2)
        }
    
    return {
        "total_lecturas": len(rows),
        "temperatura":    stats("temperatura"),
        "humedad":        stats("humedad"),
        "presion":        stats("presion"),
        "altitud":        stats("altitud")
    }

# ─── Tool 5: detector de alertas meteorológicas ─────────────────────────────
@mcp.tool()
def detectar_alertas() -> dict:
    """Detecta alertas meteorológicas basadas en la última lectura del sensor.
    Criterios: temp ≥35°C alta, ≤15°C baja, humedad ≥85% elevada, presión <1000 hPa posible lluvia."""
    data = _query(limit=1)
    if not data:
        return {"estado": "Sin datos", "alertas": []}
    
    r = data[0]
    alertas = []
    # Umbrales configurables — aquí están hardcodeados según el modelo del profesor
    if r["temperatura"] >= 35: alertas.append("Temperatura alta")
    if r["temperatura"] <= 15: alertas.append("Temperatura baja")
    if r["humedad"]     >= 85: alertas.append("Humedad elevada")
    if r["presion"]     < 1000: alertas.append("Posible lluvia")
    
    return {
        "estado":  "Con alertas" if alertas else "Normal",
        "alertas": alertas,
        "lectura": r
    }
@mcp.tool()
def obtener_promedio_por_dia(limite_dias: int = 30) -> list:
    """Calcula el promedio diario de temperatura, humedad, presión y altitud.
    Usar cuando se soliciten promedios por día o tendencias diarias."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=created_at,temperatura,humedad,presion,altitud&order=created_at.desc&limit={limite_dias * 288}",
        headers=HEADERS_READ
    )
    rows = res.json()
    
    from collections import defaultdict
    dias = defaultdict(list)
    for r in rows:
        dia = r["created_at"][:10]
        dias[dia].append(r)
    
    resultado = []
    for dia, lecturas in sorted(dias.items(), reverse=True):
        def avg(field):
            vals = [l[field] for l in lecturas if l.get(field) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None
        resultado.append({
            "fecha": dia,
            "total_lecturas": len(lecturas),
            "temperatura_promedio": avg("temperatura"),
            "humedad_promedio":     avg("humedad"),
            "presion_promedio":     avg("presion"),
            "altitud_promedio":     avg("altitud")
        })
    return resultado


@mcp.tool()
def obtener_extremos_por_dia(limite_dias: int = 30) -> list:
    """Obtiene máximos y mínimos por día. Útil para detectar días críticos o atípicos."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=created_at,temperatura,humedad,presion,altitud&order=created_at.desc&limit={limite_dias * 288}",
        headers=HEADERS_READ
    )
    rows = res.json()
    
    from collections import defaultdict
    dias = defaultdict(list)
    for r in rows:
        dia = r["created_at"][:10]
        dias[dia].append(r)
    
    resultado = []
    for dia, lecturas in sorted(dias.items(), reverse=True):
        def mx(f): vals = [l[f] for l in lecturas if l.get(f)]; return round(max(vals), 2) if vals else None
        def mn(f): vals = [l[f] for l in lecturas if l.get(f)]; return round(min(vals), 2) if vals else None
        resultado.append({
            "fecha": dia,
            "temperatura": {"max": mx("temperatura"), "min": mn("temperatura")},
            "humedad":     {"max": mx("humedad"),     "min": mn("humedad")},
            "presion":     {"max": mx("presion"),     "min": mn("presion")},
        })
    return resultado


@mcp.tool()
def detectar_anomalias(limite: int = 200, umbral_desviaciones: float = 2.0) -> list:
    """Detecta lecturas anómalas usando desviación estándar.
    Retorna registros donde algún valor se desvía más de N sigmas del promedio."""
    import math
    rows = _query(limit=limite)
    if not rows:
        return []
    
    def stats(field):
        vals = [r[field] for r in rows if r.get(field) is not None]
        avg = sum(vals) / len(vals)
        std = math.sqrt(sum((v - avg) ** 2 for v in vals) / len(vals))
        return avg, std
    
    campos = ["temperatura", "humedad", "presion", "altitud"]
    parametros = {c: stats(c) for c in campos}
    
    anomalias = []
    for r in rows:
        razones = []
        for c in campos:
            avg, std = parametros[c]
            if std > 0 and r.get(c) is not None:
                if abs(r[c] - avg) > umbral_desviaciones * std:
                    razones.append(f"{c}={r[c]} (avg={round(avg,2)}, σ={round(std,2)})")
        if razones:
            anomalias.append({"registro": r, "anomalias": razones})
    return anomalias


@mcp.tool()
def obtener_tendencia_reciente(ventana: int = 10) -> dict:
    """Compara el promedio de las últimas N lecturas contra el promedio general.
    Indica si cada variable está subiendo, bajando o estable."""
    todas = _query(limit=100)
    recientes = _query(limit=ventana)
    if not todas or not recientes:
        return {"error": "Sin datos"}
    
    def avg(rows, field):
        vals = [r[field] for r in rows if r.get(field) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    
    resultado = {}
    for campo in ["temperatura", "humedad", "presion", "altitud"]:
        general = avg(todas, campo)
        reciente = avg(recientes, campo)
        if general is None or reciente is None:
            tendencia = "sin datos"
        elif reciente > general * 1.02:
            tendencia = "subiendo"
        elif reciente < general * 0.98:
            tendencia = "bajando"
        else:
            tendencia = "estable"
        resultado[campo] = {"promedio_general": general, "promedio_reciente": reciente, "tendencia": tendencia}
    return resultado


@mcp.tool()
def contar_alertas_por_dia(limite_dias: int = 30) -> list:
    """Cuenta cuántas veces se disparó cada tipo de alerta por día.
    Útil para identificar días problemáticos."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=created_at,temperatura,humedad,presion&order=created_at.desc&limit={limite_dias * 288}",
        headers=HEADERS_READ
    )
    rows = res.json()
    
    from collections import defaultdict
    dias = defaultdict(lambda: {"temp_alta": 0, "temp_baja": 0, "humedad_elevada": 0, "posible_lluvia": 0, "total": 0})
    
    for r in rows:
        dia = r["created_at"][:10]
        dias[dia]["total"] += 1
        if r.get("temperatura", 0) >= 35:  dias[dia]["temp_alta"] += 1
        if r.get("temperatura", 100) <= 15: dias[dia]["temp_baja"] += 1
        if r.get("humedad", 0) >= 85:       dias[dia]["humedad_elevada"] += 1
        if r.get("presion", 9999) < 1000:   dias[dia]["posible_lluvia"] += 1
    
    return [{"fecha": dia, **conteos} for dia, conteos in sorted(dias.items(), reverse=True)]
# ─── Tool 6: paquete completo para dashboard ────────────────────────────────
@mcp.tool()
def datos_para_dashboard(limite: int = 100) -> dict:
    """Obtiene todos los datos necesarios para construir un dashboard completo:
    última lectura, resumen estadístico, alertas, histórico para gráficos y tabla."""
    # Combina las tools anteriores en una sola respuesta
    return {
        "ultima_lectura": obtener_ultima_lectura(),
        "resumen":        obtener_resumen_estacion(limite),
        "alertas":        detectar_alertas(),
        "historico":      obtener_datos_grafico(limite),
        "tabla":          obtener_ultimas_lecturas(20)
    }
#Promp para ver el dashboard en el LLM
@mcp.tool()
def obtener_info_proyecto() -> dict:
    """Retorna información general del proyecto y enlaces públicos.
    Usar cuando el usuario pregunte qué es esto o cómo acceder al dashboard."""
    return {
        "nombre": "Estación Meteorológica IoT",
        "dashboard": "https://medidor-metereologico.web.app/",
        "mcp_sse":   "https://linnie-noncommemoratory-overforwardly.ngrok-free.dev/sse",
        "descripcion": "Sensor BME280 + ESP32 → HiveMQ → Python → Supabase → Dashboard"
    }
# ─── Prompts MCP — plantillas pre-armadas para el LLM ───────────────────────
# Los prompts son instrucciones que el cliente MCP puede invocar con parámetros
# El LLM las recibe como contexto y las usa para guiar su respuesta

@mcp.prompt()
def prompt_dashboard_personalizado(tipo_dashboard: str = "ejecutivo", limite: int = 100) -> str:
    """Genera un dashboard meteorológico personalizado en HTML."""
    return f"""Crea un dashboard meteorológico tipo {tipo_dashboard} usando los datos de la herramienta datos_para_dashboard(limite={limite}).
El dashboard debe incluir:
- KPIs principales con la última lectura
- Gráficos interactivos con Chart.js
- Sección de alertas automáticas
- Tabla de las últimas 20 lecturas
- Conclusiones del análisis

Devuelve una página HTML completa, autocontenida, con estilos modernos."""

@mcp.prompt()
def prompt_dashboard_tendencias(fecha_inicio: str, fecha_fin: str) -> str:
    """Genera análisis de tendencias entre dos fechas."""
    return f"""Analiza las tendencias meteorológicas entre {fecha_inicio} y {fecha_fin} usando obtener_datos_grafico.
Genera:
- Gráficos de serie temporal
- Detección de picos máximos y mínimos
- Cambios bruscos en las variables
- Estadísticas completas
- Conclusiones automáticas

Devuelve una página web HTML estilo Power BI/Grafana."""

# ─── Bridge MQTT — recibe datos del ESP32 y los inserta en Supabase ────────
def on_connect(client, userdata, flags, reason_code, properties):
    """Callback al conectar al broker HiveMQ. rc=0 indica éxito."""
    print(f"MQTT conectado, rc={reason_code}")
    client.subscribe(MQTT_TOPIC)  # Se suscribe al tópico del sensor

def on_message(client, userdata, msg):
    """Callback al recibir un mensaje del ESP32.
    1. Decodifica el JSON del payload
    2. Inserta en Supabase con service_role (bypasea RLS)
    3. Imprime el resultado para diagnóstico"""
    data = json.loads(msg.payload.decode())
    response = httpx.post(
        f"{SUPABASE_URL}/rest/v1/sensor_data",
        json=data,
        headers=HEADERS_WRITE  # Service role — autorizado a escribir
    )
    print(f"Insertado: {data} → {response.status_code}")
def start_mqtt():
    try:
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
        mqtt_client.tls_set()
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.connect(MQTT_HOST, MQTT_PORT)
        mqtt_client.loop_forever()
    except Exception as e:
        print(f"Error MQTT: {e}")

threading.Thread(target=start_mqtt, daemon=True).start()
print("Bridge MQTT + MCP iniciados")
