import json
import httpx
import math
from collections import defaultdict
from fastmcp import FastMCP
import os

# ─── Variables de entorno ───────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ─── Headers con anon key — respeta politicas RLS de solo lectura ──────────
HEADERS_READ = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ─── Servidor MCP ───────────────────────────────────────────────────────────
mcp = FastMCP("estacion-meteorologica")

def _query(limit: int = 1, order: str = "desc"):
    """Helper interno — consulta Supabase con orden y limite parametrizados."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=*&order=created_at.{order}&limit={limit}",
        headers=HEADERS_READ
    )
    return res.json()

# ─── Tool 1: lectura mas reciente ───────────────────────────────────────────
@mcp.tool()
def obtener_ultima_lectura() -> dict:
    """Obtiene la lectura mas reciente de la estacion meteorologica.
    Usar cuando el usuario pregunte por temperatura, humedad, presion o altitud actual."""
    data = _query(limit=1)
    if not data:
        return {"error": "No hay lecturas registradas"}
    return data[0]

# ─── Tool 2: historico de N lecturas ────────────────────────────────────────
@mcp.tool()
def obtener_ultimas_lecturas(limite: int = 50) -> list:
    """Obtiene una lista de las ultimas N lecturas registradas.
    Usar cuando se requiera historico reciente o tabla de datos."""
    return _query(limit=limite)

# ─── Tool 3: datos en orden cronologico para graficos ───────────────────────
@mcp.tool()
def obtener_datos_grafico(limite: int = 100) -> list:
    """Prepara datos para construir graficos en orden cronologico ascendente.
    Usar cuando se necesite serie temporal o visualizacion historica."""
    return _query(limit=limite, order="asc")

# ─── Tool 4: estadisticas agregadas ─────────────────────────────────────────
@mcp.tool()
def obtener_resumen_estacion(limite: int = 100) -> dict:
    """Calcula estadisticas (promedio, maximo, minimo) de las ultimas N lecturas.
    Usar cuando se soliciten promedios, maximos, minimos o resumen general."""
    rows = _query(limit=limite)
    if not rows:
        return {"error": "Sin datos"}
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

# ─── Tool 5: detector de alertas meteorologicas ─────────────────────────────
@mcp.tool()
def detectar_alertas() -> dict:
    """Detecta alertas meteorologicas basadas en la ultima lectura del sensor.
    Criterios: temp >=35C alta, <=15C baja, humedad >=85% elevada, presion <1000 hPa posible lluvia."""
    data = _query(limit=1)
    if not data:
        return {"estado": "Sin datos", "alertas": []}
    r = data[0]
    alertas = []
    if r["temperatura"] >= 35: alertas.append("Temperatura alta")
    if r["temperatura"] <= 15: alertas.append("Temperatura baja")
    if r["humedad"]     >= 85: alertas.append("Humedad elevada")
    if r["presion"]     < 1000: alertas.append("Posible lluvia")
    return {
        "estado":  "Con alertas" if alertas else "Normal",
        "alertas": alertas,
        "lectura": r
    }

# ─── Tool 6: promedio diario ────────────────────────────────────────────────
@mcp.tool()
def obtener_promedio_por_dia(limite_dias: int = 30) -> list:
    """Calcula el promedio diario de temperatura, humedad, presion y altitud.
    Usar cuando se soliciten promedios por dia o tendencias diarias."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=created_at,temperatura,humedad,presion,altitud&order=created_at.desc&limit={limite_dias * 288}",
        headers=HEADERS_READ
    )
    rows = res.json()
    dias = defaultdict(list)
    for r in rows:
        dias[r["created_at"][:10]].append(r)
    resultado = []
    for dia, lecturas in sorted(dias.items(), reverse=True):
        def avg(field):
            vals = [l[field] for l in lecturas if l.get(field) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None
        resultado.append({
            "fecha": dia, "total_lecturas": len(lecturas),
            "temperatura_promedio": avg("temperatura"),
            "humedad_promedio": avg("humedad"),
            "presion_promedio": avg("presion"),
            "altitud_promedio": avg("altitud")
        })
    return resultado

# ─── Tool 7: extremos diarios ──────────────────────────────────────────────
@mcp.tool()
def obtener_extremos_por_dia(limite_dias: int = 30) -> list:
    """Obtiene maximos y minimos por dia. Util para detectar dias criticos."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=created_at,temperatura,humedad,presion,altitud&order=created_at.desc&limit={limite_dias * 288}",
        headers=HEADERS_READ
    )
    rows = res.json()
    dias = defaultdict(list)
    for r in rows:
        dias[r["created_at"][:10]].append(r)
    resultado = []
    for dia, lecturas in sorted(dias.items(), reverse=True):
        def mx(f):
            vals = [l[f] for l in lecturas if l.get(f)]
            return round(max(vals), 2) if vals else None
        def mn(f):
            vals = [l[f] for l in lecturas if l.get(f)]
            return round(min(vals), 2) if vals else None
        resultado.append({
            "fecha": dia,
            "temperatura": {"max": mx("temperatura"), "min": mn("temperatura")},
            "humedad":     {"max": mx("humedad"),     "min": mn("humedad")},
            "presion":     {"max": mx("presion"),     "min": mn("presion")},
        })
    return resultado

# ─── Tool 8: deteccion de anomalias por desviacion estandar ────────────────
@mcp.tool()
def detectar_anomalias(limite: int = 200, umbral_desviaciones: float = 2.0) -> list:
    """Detecta lecturas anomalas usando desviacion estandar.
    Retorna registros donde algun valor se desvia mas de N sigmas del promedio."""
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
                    razones.append(f"{c}={r[c]} (avg={round(avg,2)}, std={round(std,2)})")
        if razones:
            anomalias.append({"registro": r, "anomalias": razones})
    return anomalias

# ─── Tool 9: tendencia reciente ─────────────────────────────────────────────
@mcp.tool()
def obtener_tendencia_reciente(ventana: int = 10) -> dict:
    """Compara el promedio de las ultimas N lecturas contra el promedio general.
    Indica si cada variable esta subiendo, bajando o estable."""
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

# ─── Tool 10: conteo de alertas por dia ─────────────────────────────────────
@mcp.tool()
def contar_alertas_por_dia(limite_dias: int = 30) -> list:
    """Cuenta cuantas veces se disparo cada tipo de alerta por dia."""
    res = httpx.get(
        f"{SUPABASE_URL}/rest/v1/sensor_data?select=created_at,temperatura,humedad,presion&order=created_at.desc&limit={limite_dias * 288}",
        headers=HEADERS_READ
    )
    rows = res.json()
    dias = defaultdict(lambda: {"temp_alta": 0, "temp_baja": 0, "humedad_elevada": 0, "posible_lluvia": 0, "total": 0})
    for r in rows:
        dia = r["created_at"][:10]
        dias[dia]["total"] += 1
        if r.get("temperatura", 0) >= 35:   dias[dia]["temp_alta"] += 1
        if r.get("temperatura", 100) <= 15: dias[dia]["temp_baja"] += 1
        if r.get("humedad", 0) >= 85:       dias[dia]["humedad_elevada"] += 1
        if r.get("presion", 9999) < 1000:   dias[dia]["posible_lluvia"] += 1
    return [{"fecha": dia, **conteos} for dia, conteos in sorted(dias.items(), reverse=True)]

# ─── Tool 11: paquete completo para dashboard ──────────────────────────────
@mcp.tool()
def datos_para_dashboard(limite: int = 100) -> dict:
    """Obtiene todos los datos necesarios para construir un dashboard completo."""
    return {
        "ultima_lectura": obtener_ultima_lectura(),
        "resumen":        obtener_resumen_estacion(limite),
        "alertas":        detectar_alertas(),
        "historico":      obtener_datos_grafico(limite),
        "tabla":          obtener_ultimas_lecturas(20)
    }

# ─── Tool 12: informacion del proyecto ──────────────────────────────────────
@mcp.tool()
def obtener_info_proyecto() -> dict:
    """Retorna informacion general del proyecto y enlaces publicos."""
    return {
        "nombre": "Estacion Meteorologica IoT",
        "dashboard": "https://medidor-metereologico.web.app/",
        "mcp": "https://identical-apricot-hoverfly.fastmcp.app/mcp",
        "descripcion": "Sensor BME280 + ESP32 -> HiveMQ -> Python -> Supabase -> Dashboard"
    }

# ─── Prompts MCP ────────────────────────────────────────────────────────────
@mcp.prompt()
def prompt_dashboard_personalizado(tipo_dashboard: str = "ejecutivo", limite: int = 100) -> str:
    """Genera un dashboard meteorologico personalizado en HTML."""
    return f"""Crea un dashboard meteorologico tipo {tipo_dashboard} usando datos_para_dashboard(limite={limite}).
Incluir: KPIs, graficos Chart.js, alertas, tabla de 20 lecturas, conclusiones.
Devuelve HTML completo autocontenido con estilos modernos."""

@mcp.prompt()
def prompt_dashboard_tendencias(fecha_inicio: str, fecha_fin: str) -> str:
    """Genera analisis de tendencias entre dos fechas."""
    return f"""Analiza tendencias meteorologicas entre {fecha_inicio} y {fecha_fin} usando obtener_datos_grafico.
Incluir: graficos temporales, picos, cambios bruscos, estadisticas, conclusiones.
Devuelve HTML estilo Power BI/Grafana."""
