import logging
import traceback
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from apscheduler.schedulers.background import BackgroundScheduler
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os

# --- CONFIGURACIÓN ---
TOKEN = "7992552839:AAEA54Yi1MIS1Wfrq0xkFL0E-LgW3rMbyqo"

# Archivo para almacenar usuarios registrados
USUARIOS_FILE = "usuarios_registrados.json"

# Diccionario para almacenar usuarios activos
usuarios_registrados = {}

# Mapeo extendido de tickers argentinos con alternativas
TICKERS_ARGENTINOS = {
    "YPF": ["YPF", "YPF.BA", "YPFD"],
    "GGAL": ["GGAL", "GGAL.BA"],
    "BMA": ["BMA", "BMA.BA"],
    "PAMP": ["PAMP", "PAMP.BA"],
    "TXAR": ["TXAR", "TXAR.BA", "TX"], # Added TX as common short for TXAR
    "ALUA": ["ALUA", "ALUA.BA"],
    "TECO2": ["TECO2", "TECO2.BA"],
    "MIRG": ["MIRG", "MIRG.BA"],
    "SUPV": ["SUPV", "SUPV.BA"],
    "CRES": ["CRES", "CRES.BA"],
    "TRAN": ["TRAN", "TRAN.BA"],
    "LOMA": ["LOMA", "LOMA.BA"],
    "CEPU": ["CEPU", "CEPU.BA"],
    "COME": ["COME", "COME.BA"],
    "BYMA": ["BYMA", "BYMA.BA"],
}

def cargar_usuarios():
    """Carga la lista de usuarios registrados desde archivo"""
    global usuarios_registrados
    try:
        if os.path.exists(USUARIOS_FILE):
            with open(USUARIOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                usuarios_registrados = {int(k): v for k, v in data.items()}
        else:
            usuarios_registrados = {}
        print(f"✅ Usuarios cargados: {len(usuarios_registrados)}")
    except Exception as e:
        print(f"❌ Error cargando usuarios: {e}")
        usuarios_registrados = {}

def guardar_usuarios():
    """Guarda la lista de usuarios registrados en archivo"""
    try:
        with open(USUARIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(usuarios_registrados, f, ensure_ascii=False, indent=2)
        print(f"💾 Usuarios guardados: {len(usuarios_registrados)}")
    except Exception as e:
        print(f"❌ Error guardando usuarios: {e}")

def registrar_usuario(chat_id, username, first_name, last_name=None):
    """Registra un nuevo usuario"""
    global usuarios_registrados
    
    usuario_info = {
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "fecha_registro": datetime.now().isoformat(),
        "alertas_activas": True,
        "acciones_favoritas": [],
        "setup_completo": False
    }
    
    usuarios_registrados[chat_id] = usuario_info
    guardar_usuarios()
    
    print(f"👤 Nuevo usuario registrado: {username} ({chat_id})")
    return True

def crear_menu_principal():
    """Crea el menú principal con 3 botones principales"""
    keyboard = [
        [
            InlineKeyboardButton("⭐ Mis Favoritas", callback_data="favoritas")
        ],
        [
            InlineKeyboardButton("📊 Analizar Cualquier Acción", callback_data="analizar_cualquier")
        ],
        [
            InlineKeyboardButton("📈 Top 10 del Día", callback_data="top_10_dia")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def crear_menu_setup_inicial():
    """Menú para el setup inicial obligatorio"""
    keyboard = [
        [
            InlineKeyboardButton("🇺🇸 Acciones USA Populares", callback_data="setup_usa"),
            InlineKeyboardButton("🇦🇷 Acciones Argentinas", callback_data="setup_argentinas")
        ],
        [
            InlineKeyboardButton("✍️ Escribir Manualmente", callback_data="setup_manual"),
            InlineKeyboardButton("🔥 Sugerencias Top", callback_data="setup_sugerencias")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def crear_menu_sugerencias_setup():
    """Menú con sugerencias para setup inicial"""
    keyboard = [
        [
            InlineKeyboardButton("🟢 AAPL", callback_data="add_setup_AAPL"),
            InlineKeyboardButton("🟢 TSLA", callback_data="add_setup_TSLA"),
            InlineKeyboardButton("🟢 MSFT", callback_data="add_setup_MSFT")
        ],
        [
            InlineKeyboardButton("🔵 YPF", callback_data="add_setup_YPF"),
            InlineKeyboardButton("🔵 GGAL", callback_data="add_setup_GGAL"),
            InlineKeyboardButton("🔵 BMA", callback_data="add_setup_BMA")
        ],
        [
            InlineKeyboardButton("🔥 NVDA", callback_data="add_setup_NVDA"),
            InlineKeyboardButton("🔥 GOOGL", callback_data="add_setup_GOOGL"),
            InlineKeyboardButton("🔥 META", callback_data="add_setup_META")
        ],
        [
            InlineKeyboardButton("✅ Terminar Setup", callback_data="finalizar_setup"),
            InlineKeyboardButton("🔙 Volver", callback_data="setup_inicial")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def obtener_datos_accion(ticker_original):
    """Intenta obtener datos de una acción probando diferentes variantes del ticker"""
    ticker = ticker_original.upper().strip()
    
    # Lista extendida de variantes a probar
    variantes = []
    
    # Si es un ticker argentino conocido, usar las alternativas
    ticker_base = ticker.replace('.BA', '').replace('.AR', '').replace('.NYSE', '').replace('.NASDAQ', '')
    if ticker_base in TICKERS_ARGENTINOS:
        variantes.extend(TICKERS_ARGENTINOS[ticker_base])
    
    # Agregar variantes comunes para todos los tickers
    variantes.extend([
        ticker,                    # Ticker original
        f"{ticker}.BA",           # Buenos Aires
        f"{ticker}.AR",           # Argentina
        f"{ticker_base}",         # Sin sufijos
        f"{ticker_base}.BA",      # Base + BA
        f"{ticker_base}.NYSE",    # NYSE
        f"{ticker_base}.NASDAQ",  # NASDAQ
    ])
    
    # Eliminar duplicados manteniendo el orden
    variantes = list(dict.fromkeys(variantes))
    
    print(f"🔍 Probando variantes para {ticker_original}: {variantes[:5]}...") # Show more variants in log
    
    for i, variante in enumerate(variantes):
        try:
            print(f"  Intentando {i+1}/{len(variantes)}: {variante}")
            # Changed period back to 6mo for better indicator calculation
            df = yf.download(variante, period='6mo', interval='1d', progress=False, show_errors=False)
            
            # Ensure enough data for analysis (e.g., for MACD which needs 26 periods)
            if not df.empty and 'Close' in df.columns and len(df) > 30: # Increased minimum data points
                print(f"✅ Datos encontrados para {variante}")
                return df, variante
                
        except Exception as e:
            print(f"  ❌ Error con {variante}: {str(e)[:50]}")
            continue
    
    print(f"❌ No se encontraron datos para ninguna variante de {ticker_original}")
    return None, None

def buscar_ticker_inteligente(ticker_input):
    """Búsqueda inteligente de ticker con sugerencias"""
    ticker = ticker_input.upper().strip()
    
    # Diccionario de tickers comunes y sus variantes
    TICKERS_COMUNES = {
        # USA - Tech
        'APPLE': 'AAPL', 'AAPL': 'AAPL',
        'TESLA': 'TSLA', 'TSLA': 'TSLA',
        'MICROSOFT': 'MSFT', 'MSFT': 'MSFT',
        'GOOGLE': 'GOOGL', 'GOOGL': 'GOOGL', 'GOOG': 'GOOGL',
        'AMAZON': 'AMZN', 'AMZN': 'AMZN',
        'NVIDIA': 'NVDA', 'NVDA': 'NVDA',
        'META': 'META', 'FACEBOOK': 'META',
        'NETFLIX': 'NFLX', 'NFLX': 'NFLX',
        'AMD': 'AMD',
        
        # Argentina
        'YPF': 'YPF', 'YPFD': 'YPF',
        'GALICIA': 'GGAL', 'GGAL': 'GGAL',
        'MACRO': 'BMA', 'BMA': 'BMA',
        'PAMPA': 'PAMP', 'PAMP': 'PAMP',
        'TERNIUM': 'TX', 'TX': 'TX', # Added TX for Ternium
        'ALUAR': 'ALUA', 'ALUA': 'ALUA',
    }
    
    # Buscar coincidencia exacta o por nombre
    if ticker in TICKERS_COMUNES:
        return TICKERS_COMUNES[ticker]
    
    # Buscar coincidencias parciales
    for nombre, simbolo in TICKERS_COMUNES.items():
        if ticker in nombre or nombre in ticker:
            return simbolo
    
    return ticker

def validar_ticker_con_sugerencias(ticker_input):
    """Valida un ticker y proporciona sugerencias si falla"""
    # Limpiar input
    ticker_limpio = buscar_ticker_inteligente(ticker_input)
    
    # Intentar obtener datos
    df, ticker_encontrado = obtener_datos_accion(ticker_limpio)
    
    if df is not None:
        return True, ticker_encontrado, None
    
    # Si falla, generar sugerencias
    sugerencias = generar_sugerencias_ticker(ticker_input)
    return False, None, sugerencias

def generar_sugerencias_ticker(ticker_input):
    """Genera sugerencias cuando un ticker no se encuentra"""
    ticker = ticker_input.upper().strip()
    
    sugerencias = []
    
    # Sugerencias basadas en similitud
    SUGERENCIAS_COMUNES = {
        'APPL': 'AAPL (Apple)',
        'TESLAS': 'TSLA (Tesla)', 
        'TESLA': 'TSLA (Tesla)',
        'MICROSFT': 'MSFT (Microsoft)',
        'MICROSOFT': 'MSFT (Microsoft)',
        'GOOGEL': 'GOOGL (Google)',
        'GOOGLE': 'GOOGL (Google)',
        'AMAZN': 'AMZN (Amazon)',
        'AMAZON': 'AMZN (Amazon)',
        'NVIDEA': 'NVDA (Nvidia)',
        'NVIDIA': 'NVDA (Nvidia)',
        'FACEBOOK': 'META (Meta/Facebook)',
        'GALICIA': 'GGAL (Banco Galicia)',
        'MACRO': 'BMA (Banco Macro)',
        'PAMPA': 'PAMP (Pampa Energía)',
        'TERNIUM': 'TX (Ternium Argentina)', # Added Ternium
    }
    
    # Buscar sugerencias exactas
    if ticker in SUGERENCIAS_COMUNES:
        sugerencias.append(SUGERENCIAS_COMUNES[ticker])
    
    # Buscar sugerencias por similitud
    for error_comun, sugerencia in SUGERENCIAS_COMUNES.items():
        if abs(len(ticker) - len(error_comun)) <= 2:  # Longitud similar
            coincidencias = sum(1 for a, b in zip(ticker, error_comun) if a == b)
            if coincidencias >= len(ticker) - 2:  # Máximo 2 diferencias
                sugerencias.append(sugerencia)
    
    # Agregar sugerencias populares si no hay coincidencias
    if not sugerencias:
        sugerencias = [
            'AAPL (Apple)', 'TSLA (Tesla)', 'MSFT (Microsoft)',
            'GOOGL (Google)', 'YPF (YPF)', 'GGAL (Galicia)'
        ]
    
    return list(dict.fromkeys(sugerencias))[:3]  # Máximo 3 sugerencias, sin duplicados

def normalizar_datos(datos):
    """Normaliza los datos para asegurar que sean 1D"""
    if isinstance(datos, pd.Series):
        return datos.values.flatten()
    elif isinstance(datos, np.ndarray):
        return datos.flatten()
    elif isinstance(datos, list):
        return np.array(datos).flatten()
    else:
        return np.array(datos).flatten()

def calcular_rsi(precios, periodo=14):
    """Calcula el RSI (Relative Strength Index)"""
    try:
        precios_array = normalizar_datos(precios)
        
        if len(precios_array) < periodo + 1:
            return None
        
        deltas = np.diff(precios_array)
        ganancias = np.where(deltas > 0, deltas, 0)
        perdidas = np.where(deltas < 0, -deltas, 0)
        
        ganancia_promedio = np.mean(ganancias[-periodo:])
        perdida_promedio = np.mean(perdidas[-periodo:])
        
        if perdida_promedio == 0:
            return 100
        
        rs = ganancia_promedio / perdida_promedio
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        print(f"Error en RSI: {e}")
        return None

def calcular_macd(precios):
    """Calcula el MACD"""
    try:
        precios_array = normalizar_datos(precios)
        
        if len(precios_array) < 26:
            return None, None, None
        
        precios_series = pd.Series(precios_array)
        
        ema12 = precios_series.ewm(span=12).mean()
        ema26 = precios_series.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line
        
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
    except Exception as e:
        print(f"Error en MACD: {e}")
        return None, None, None

def detectar_zonas(data, tolerancia=0.02):
    """Detecta zonas de soporte y resistencia"""
    try:
        if 'Close' not in data.columns:
            return {'soportes': [], 'resistencias': []}
        
        precios = normalizar_datos(data['Close'])
        zonas = {'soportes': [], 'resistencias': []}
        
        if len(precios) < 20:
            return zonas
        
        for i in range(10, len(precios) - 10):
            ventana = precios[i-10:i+10]
            precio_actual = float(precios[i])
            
            # Detectar máximos locales (resistencias)
            if precio_actual == max(ventana):
                zonas['resistencias'].append(precio_actual)
            
            # Detectar mínimos locales (soportes)
            if precio_actual == min(ventana):
                zonas['soportes'].append(precio_actual)
        
        # Eliminar duplicados cercanos
        zonas['soportes'] = list(set([round(x, 2) for x in zonas['soportes']]))
        zonas['resistencias'] = list(set([round(x, 2) for x in zonas['resistencias']]))
        
        return zonas
    except Exception as e:
        print(f"Error en detectar_zonas: {e}")
        return {'soportes': [], 'resistencias': []}

def analizar_fundamental(ticker, data):
    """Análisis fundamental básico y sugerencias de trading"""
    try:
        precio_actual = float(data['Close'].iloc[-1])
        precios = normalizar_datos(data['Close'])
        
        # Calcular promedios móviles
        ma20 = np.mean(precios[-20:]) if len(precios) >= 20 else precio_actual
        ma50 = np.mean(precios[-50:]) if len(precios) >= 50 else precio_actual
        
        # Calcular volatilidad
        volatilidad = np.std(precios[-20:]) if len(precios) >= 20 else 0
        vol_porcentaje = (volatilidad / precio_actual) * 100
        
        # Calcular RSI
        rsi = calcular_rsi(precios)
        
        # Calcular MACD
        macd, signal, histogram = calcular_macd(precios)
        
        sugerencias = []
        
        # Lógica de sugerencias basada en análisis técnico y fundamental
        if rsi and rsi < 30:
            if precio_actual < ma20 and precio_actual < ma50:
                sugerencias.append("🟢 OPORTUNIDAD DE COMPRA: RSI sobrevendido + precio bajo promedios móviles")
                sugerencias.append("💡 Mi sugerencia: Esperaría a ver una confirmación de rebote antes de comprar")
            else:
                sugerencias.append("🟡 POSIBLE COMPRA: RSI sobrevendido, pero precio aún elevado")
                sugerencias.append("💡 Mi sugerencia: No me adelantaría, esperaría a que baje más o confirme soporte")
        
        elif rsi and rsi > 70:
            if precio_actual > ma20 and precio_actual > ma50:
                sugerencias.append("🔴 SEÑAL DE VENTA: RSI sobrecomprado + precio sobre promedios móviles")
                sugerencias.append("💡 Mi sugerencia: Yo consideraría tomar ganancias o al menos reducir posición")
            else:
                sugerencias.append("🟡 PRECAUCIÓN: RSI sobrecomprado, posible corrección")
                sugerencias.append("💡 Mi sugerencia: Esperaría a que se corrija antes de entrar")
        
        else:
            # Análisis MACD para zona neutral
            if macd and signal and histogram:
                if macd > signal and histogram > 0:
                    sugerencias.append("🟢 MOMENTUM ALCISTA: MACD positivo")
                    sugerencias.append("💡 Mi sugerencia: Buena oportunidad para mantener o entrar con stop loss")
                elif macd < signal and histogram < 0:
                    sugerencias.append("🔴 MOMENTUM BAJISTA: MACD negativo")
                    sugerencias.append("💡 Mi sugerencia: Esperaría a que mejore el momentum antes de comprar")
                else:
                    sugerencias.append("🟡 INDECISIÓN: Señales mixtas")
                    sugerencias.append("💡 Mi sugerencia: Esperaría definición clara antes de actuar")
        
        # Análisis de volatilidad
        if vol_porcentaje > 5:
            sugerencias.append(f"⚡ ALTA VOLATILIDAD ({vol_porcentaje:.1f}%): Mayor riesgo, posiciones más pequeñas")
        elif vol_porcentaje < 2:
            sugerencias.append(f"😴 BAJA VOLATILIDAD ({vol_porcentaje:.1f}%): Movimientos limitados, paciencia")
        
        # Análisis de tendencia
        if precio_actual > ma20 > ma50:
            sugerencias.append("📈 TENDENCIA ALCISTA: Precio sobre ambos promedios móviles")
        elif precio_actual < ma20 < ma50:
            sugerencias.append("📉 TENDENCIA BAJISTA: Precio bajo ambos promedios móviles")
        else:
            sugerencias.append("➡️ TENDENCIA LATERAL: Sin dirección clara")
        
        return sugerencias
    
    except Exception as e:
        print(f"Error en análisis fundamental: {e}")
        return ["❌ Error en análisis fundamental"]

def evaluar_oportunidad_trading(ticker, data, zonas):
    """Evalúa si es una oportunidad 100% efectiva para comprar/vender"""
    try:
        precio_actual = float(data['Close'].iloc[-1])
        precios = normalizar_datos(data['Close'])
        
        # Calcular indicadores
        rsi = calcular_rsi(precios)
        macd, signal, histogram = calcular_macd(precios)
        
        # Calcular promedios móviles
        ma5 = np.mean(precios[-5:]) if len(precios) >= 5 else precio_actual
        ma20 = np.mean(precios[-20:]) if len(precios) >= 20 else precio_actual
        
        oportunidad = {
            'es_oportunidad': False,
            'tipo': None,
            'confianza': 0,
            'razon': []
        }
        
        puntos_compra = 0
        puntos_venta = 0
        
        # Evaluar oportunidad de COMPRA
        if rsi and rsi < 30:
            puntos_compra += 3
            oportunidad['razon'].append("RSI sobrevendido (<30)")
        
        if precio_actual < ma20 * 0.95:  # 5% bajo MA20
            puntos_compra += 2
            oportunidad['razon'].append("Precio 5% bajo MA20")
        
        if macd and signal and macd > signal and histogram > 0:
            puntos_compra += 2
            oportunidad['razon'].append("MACD cruzando al alza")
        
        # Verificar proximidad a soporte
        if len(zonas['soportes']) > 0:
            soporte_cercano = min(zonas['soportes'], key=lambda x: abs(x - precio_actual))
            if abs(precio_actual - soporte_cercano) / precio_actual < 0.02:  # 2% de tolerancia
                puntos_compra += 3
                oportunidad['razon'].append(f"Cerca de soporte fuerte (${soporte_cercano:.2f})")
        
        # Evaluar oportunidad de VENTA
        if rsi and rsi > 70:
            puntos_venta += 3
            oportunidad['razon'].append("RSI sobrecomprado (>70)")
        
        if precio_actual > ma20 * 1.05:  # 5% sobre MA20
            puntos_venta += 2
            oportunidad['razon'].append("Precio 5% sobre MA20")
        
        if macd and signal and macd < signal and histogram < 0:
            puntos_venta += 2
            oportunidad['razon'].append("MACD cruzando a la baja")
        
        # Verificar proximidad a resistencia
        if len(zonas['resistencias']) > 0:
            resistencia_cercana = min(zonas['resistencias'], key=lambda x: abs(x - precio_actual))
            if abs(precio_actual - resistencia_cercana) / precio_actual < 0.02:  # 2% de tolerancia
                puntos_venta += 3
                oportunidad['razon'].append(f"Cerca de resistencia fuerte (${resistencia_cercana:.2f})")
        
        # Determinar oportunidad
        if puntos_compra >= 5:
            oportunidad['es_oportunidad'] = True
            oportunidad['tipo'] = 'COMPRA'
            oportunidad['confianza'] = min(puntos_compra * 10, 100)
        elif puntos_venta >= 5:
            oportunidad['es_oportunidad'] = True
            oportunidad['tipo'] = 'VENTA'
            oportunidad['confianza'] = min(puntos_venta * 10, 100)
        
        return oportunidad
    
    except Exception as e:
        print(f"Error evaluando oportunidad: {e}")
        return {'es_oportunidad': False, 'tipo': None, 'confianza': 0, 'razon': []}

def analizar_accion_completa(ticker: str):
    """Análisis completo de una acción con sugerencias"""
    try:
        # Obtener datos
        df, ticker_usado = obtener_datos_accion(ticker)
        
        if df is None:
            return f"❌ No se encontraron datos para {ticker}", False, None
        
        precio_actual = float(df['Close'].iloc[-1])
        precio_anterior = float(df['Close'].iloc[-2])
        cambio = precio_actual - precio_anterior
        cambio_porcentaje = (cambio / precio_anterior) * 100
        
        # Detectar zonas de soporte y resistencia
        zonas = detectar_zonas(df)
        
        # Análisis técnico
        precios = normalizar_datos(df['Close'])
        rsi = calcular_rsi(precios)
        macd, signal, histogram = calcular_macd(precios)
        
        # Análisis fundamental y sugerencias
        sugerencias = analizar_fundamental(ticker_usado, df)
        
        # Evaluar oportunidad de trading
        oportunidad = evaluar_oportunidad_trading(ticker_usado, df, zonas)
        
        # Construir respuesta
        respuesta = f"📊 ANÁLISIS COMPLETO DE {ticker_usado}\n"
        respuesta += "=" * 40 + "\n"
        respuesta += f"💵 Precio actual: ${precio_actual:.2f}\n"
        
        if cambio >= 0:
            respuesta += f"📈 Cambio: +${cambio:.2f} (+{cambio_porcentaje:.2f}%)\n"
        else:
            respuesta += f"📉 Cambio: ${cambio:.2f} ({cambio_porcentaje:.2f}%)\n"
        
        # Indicadores técnicos
        respuesta += "\n📊 INDICADORES TÉCNICOS:\n"
        if rsi:
            if rsi > 70:
                respuesta += f"🔴 RSI: {rsi:.1f} (SOBRECOMPRADO)\n"
            elif rsi < 30:
                respuesta += f"🟢 RSI: {rsi:.1f} (SOBREVENDIDO)\n"
            else:
                respuesta += f"🟡 RSI: {rsi:.1f} (NEUTRAL)\n"
        
        if macd and signal:
            if macd > signal:
                respuesta += "🟢 MACD: Señal alcista\n"
            else:
                respuesta += "🔴 MACD: Señal bajista\n"
        
        # Zonas clave
        alerta = False
        if len(zonas['soportes']) > 0:
            soporte_cercano = min(zonas['soportes'], key=lambda x: abs(x - precio_actual))
            if abs(precio_actual - soporte_cercano) / precio_actual < 0.03:
                respuesta += f"\n🟢 CERCA DE SOPORTE: ${soporte_cercano:.2f}\n"
                alerta = True
        
        if len(zonas['resistencias']) > 0:
            resistencia_cercana = min(zonas['resistencias'], key=lambda x: abs(x - precio_actual))
            if abs(precio_actual - resistencia_cercana) / precio_actual < 0.03:
                respuesta += f"🔴 CERCA DE RESISTENCIA: ${resistencia_cercana:.2f}\n"
                alerta = True
        
        # Oportunidad de trading
        if oportunidad['es_oportunidad']:
            respuesta += f"\n🎯 OPORTUNIDAD DE {oportunidad['tipo']}\n"
            respuesta += f"📈 Confianza: {oportunidad['confianza']}%\n"
            respuesta += "🔍 Razones:\n"
            for razon in oportunidad['razon']:
                respuesta += f"• {razon}\n"
            alerta = True
        
        # Sugerencias
        respuesta += "\n💡 SUGERENCIAS DE TRADING:\n"
        for sugerencia in sugerencias:
            respuesta += f"{sugerencia}\n"
        
        respuesta += "\n⚠️ DISCLAIMER: Este análisis es educativo, no es consejo financiero."
        
        return respuesta, alerta, oportunidad
    
    except Exception as e:
        tb = traceback.format_exc()
        return f"⚠️ Error al analizar {ticker}: {str(e)}", False, None

# --- MANEJADORES DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = update.message.from_user
    
    # Registrar usuario si no existe
    if chat_id not in usuarios_registrados:
        registrar_usuario(
            chat_id=chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # MENSAJE EXPLICATIVO OBLIGATORIO
        mensaje_explicativo = f"""🚀 **¡BIENVENIDO {user.first_name.upper()} AL BOT DE ANÁLISIS TÉCNICO!** 🚀

🤖 **¿QUÉ HACE ESTE BOT?**

🔍 **ANÁLISIS COMPLETO + SUGERENCIAS DE TRADING:**
• 📊 **Análisis técnico:** RSI, MACD, soportes y resistencias
• 🎯 **Oportunidades 100% efectivas:** Detecta puntos clave para comprar/vender
• 💡 **Sugerencias personalizadas:** "Yo esperaría para comprar", "No me adelantaría"
• 📈 **Análisis fundamental:** Combina técnico + fundamental para mejores decisiones

🚨 **ALERTAS INTELIGENTES (cada 15 minutos):**
• Te avisa cuando tus favoritas están en puntos clave
• Detecta oportunidades de alta confianza
• Sugerencias específicas para cada situación

🌍 **MERCADOS SOPORTADOS:**
• 🇺🇸 **USA:** AAPL, TSLA, MSFT, GOOGL, AMZN, NVDA, META
• 🇦🇷 **Argentina:** YPF, GGAL, BMA, PAMP, TXAR, ALUA

⚠️ **IMPORTANTE:** Este bot es educativo, NO es consejo financiero

🎯 **PARA EMPEZAR NECESITAS AGREGAR TUS ACCIONES FAVORITAS**
👇 **¡CONFIGUREMOS TU LISTA AHORA!** 👇"""
        
        await update.message.reply_text(
            mensaje_explicativo,
            parse_mode='Markdown'
        )
        
        # Mensaje obligatorio para setup
        mensaje_setup = """⭐ **CONFIGURACIÓN OBLIGATORIA** ⭐

🎯 **Necesitas agregar al menos 3 acciones favoritas para comenzar**

📋 **Estas acciones recibirán alertas automáticas cada 15 minutos**

💡 **Elige tu método preferido:**"""
        
        await update.message.reply_text(
            mensaje_setup,
            reply_markup=crear_menu_setup_inicial(),
            parse_mode='Markdown'
        )
        
    else:
        # Verificar si completó setup
        usuario_info = usuarios_registrados[chat_id]
        if not usuario_info.get('setup_completo', False):
            await update.message.reply_text(
                f"👋 **Hola {user.first_name}** 👋\n\n⚠️ **Necesitas completar tu configuración inicial**\n\n🎯 **Agrega tus acciones favoritas para comenzar:**",
                reply_markup=crear_menu_setup_inicial(),
                parse_mode='Markdown'
            )
        else:
            # Usuario existente con setup completo
            num_favoritas = len(usuario_info.get('acciones_favoritas', []))
            
            mensaje_bienvenida = f"""👋 **¡HOLA DE NUEVO {user.first_name.upper()}!** 👋

🤖 **Bot de Análisis Técnico - Listo para usar**

📊 **Tu cuenta:**
• **Registrado:** {usuario_info['fecha_registro'][:10]}
• **Alertas:** {'🔔 ACTIVAS' if usuario_info.get('alertas_activas', True) else '🔕 DESACTIVADAS'}
• **Favoritas:** {num_favoritas} acciones configuradas

🚀 **¿Qué quieres analizar hoy?**
👇 **SELECCIONA UNA OPCIÓN** 👇"""
            
            await update.message.reply_text(
                mensaje_bienvenida,
                reply_markup=crear_menu_principal(),
                parse_mode='Markdown'
            )

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del menú"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user = query.from_user
    
    # Verificar si el usuario está registrado
    if chat_id not in usuarios_registrados:
        registrar_usuario(
            chat_id=chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    
    # Verificar si el setup está completo antes de permitir acceso a funciones principales
    # Las acciones de setup (setup_inicial, setup_sugerencias, add_setup_, finalizar_setup, setup_manual)
    # son las únicas permitidas si el setup no está completo.
    if not usuarios_registrados[chat_id].get('setup_completo', False) and \
       query.data not in ["setup_inicial", "setup_sugerencias", "finalizar_setup", "setup_manual"] and \
       not query.data.startswith("add_setup_"):
        await query.edit_message_text(
            f"⚠️ **CONFIGURACIÓN PENDIENTE** ⚠️\n\n🎯 **Necesitas completar tu setup inicial**\n\n💡 **Agrega tus acciones favoritas primero:**",
            reply_markup=crear_menu_setup_inicial(),
            parse_mode='Markdown'
        )
        return # Detener el procesamiento si el setup no está completo y no es una acción de setup
    
    # Manejar setup inicial
    if query.data == "setup_inicial":
        await query.edit_message_text(
            """⭐ **CONFIGURACIÓN INICIAL** ⭐

🎯 **Necesitas agregar al menos 3 acciones favoritas**

💡 **Elige tu método preferido:**""",
            reply_markup=crear_menu_setup_inicial(),
            parse_mode='Markdown'
        )
    
    elif query.data == "setup_sugerencias":
        usuario_info = usuarios_registrados[chat_id]
        num_favoritas = len(usuario_info.get('acciones_favoritas', []))
        
        await query.edit_message_text(
            f"""🔥 **SUGERENCIAS TOP** 🔥

📊 **Acciones más populares para alertas**
🟢 **USA** | 🔵 **Argentina** | 🔥 **Trending**

⭐ **Favoritas actuales:** {num_favoritas}
🎯 **Mínimo requerido:** 3

💡 **Presiona para agregar:**""",
            reply_markup=crear_menu_sugerencias_setup(),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("add_setup_"):
        ticker = query.data.replace("add_setup_", "")
        usuario_info = usuarios_registrados[chat_id]
        favoritas_usuario = usuario_info.get('acciones_favoritas', [])
        
        if ticker not in favoritas_usuario:
            favoritas_usuario.append(ticker)
            usuarios_registrados[chat_id]['acciones_favoritas'] = favoritas_usuario
            guardar_usuarios()
            
            await query.edit_message_text(
                f"""✅ **{ticker} agregada exitosamente**

⭐ **Favoritas actuales:** {len(favoritas_usuario)}
📋 **Lista:** {', '.join(favoritas_usuario)}

🎯 **Mínimo requerido:** 3

💡 **Continúa agregando:**""",
                reply_markup=crear_menu_sugerencias_setup(),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"""⚠️ **{ticker} ya está en tu lista**

⭐ **Favoritas actuales:** {len(favoritas_usuario)}
📋 **Lista:** {', '.join(favoritas_usuario)}

💡 **Elige otra acción:**""",
                reply_markup=crear_menu_sugerencias_setup(),
                parse_mode='Markdown'
            )
    
    elif query.data == "finalizar_setup":
        usuario_info = usuarios_registrados[chat_id]
        favoritas_usuario = usuario_info.get('acciones_favoritas', [])
        
        if len(favoritas_usuario) >= 3:
            usuarios_registrados[chat_id]['setup_completo'] = True
            guardar_usuarios()
            
            await query.edit_message_text(
                f"""🎉 **¡CONFIGURACIÓN COMPLETADA!** 🎉

✅ **Setup exitoso:**
• **Acciones favoritas:** {len(favoritas_usuario)}
• **Lista:** {', '.join(favoritas_usuario)}
• **Alertas:** 🔔 ACTIVAS (cada 15 minutos)

🚀 **¡El bot está listo para usar!**
👇 **ACCEDE AL MENÚ PRINCIPAL** 👇""",
                reply_markup=crear_menu_principal(),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"""⚠️ **CONFIGURACIÓN INCOMPLETA**

❌ **Tienes {len(favoritas_usuario)} favoritas**
🎯 **Necesitas al menos 3**

💡 **Agrega más acciones:**""",
                reply_markup=crear_menu_sugerencias_setup(),
                parse_mode='Markdown'
            )
    
    elif query.data == "setup_manual":
        await query.edit_message_text(
            """✍️ **AGREGAR MANUALMENTE** ✍️

📝 **Escribe el símbolo de la acción**

🔥 **EJEMPLOS:**
• **USA:** AAPL, TSLA, MSFT, GOOGL, AMZN
• **Argentina:** YPF, GGAL, BMA, PAMP

💡 **Tips:**
• Puedes escribir en minúsculas
• Para Argentina: YPF o YPF.BA
• Una acción por mensaje

🎯 **Escribe el ticker ahora:**""",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="setup_inicial")]])
        )
        
        context.user_data['modo'] = 'setup_manual'
    
    # --- NUEVOS BOTONES DEL MENÚ PRINCIPAL ---
    elif query.data == "menu":
        await query.edit_message_text(
            "🤖 **MENÚ PRINCIPAL** 🤖\n\n🎯 **¿Qué análisis quieres hacer?**\n👇 **Selecciona una opción** 👇",
            reply_markup=crear_menu_principal(),
            parse_mode='Markdown'
        )
    
    elif query.data == "favoritas":
        usuario_info = usuarios_registrados[chat_id]
        favoritas_usuario = usuario_info.get('acciones_favoritas', [])
        
        favoritas_texto = f"⭐ **MIS ACCIONES FAVORITAS** ⭐\n\n🚨 **Alertas inteligentes {'ACTIVAS' if usuario_info.get('alertas_activas', True) else 'DESACTIVADAS'}**\n\n"
        for i, accion in enumerate(favoritas_usuario, 1):
            favoritas_texto += f"{i}. **{accion}**\n"
        favoritas_texto += f"\n📊 **Total: {len(favoritas_usuario)} acciones**\n🎯 **Presiona para análisis completo:**"
        
        keyboard = []
        for i in range(0, len(favoritas_usuario), 2):
            row = []
            for j in range(2):
                if i + j < len(favoritas_usuario):
                    accion = favoritas_usuario[i + j]
                    row.append(InlineKeyboardButton(f"📊 {accion}", callback_data=f"analizar_{accion}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Volver al Menú", callback_data="menu")])
        
        await query.edit_message_text(
            favoritas_texto,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("analizar_"):
        ticker = query.data.replace("analizar_", "")
        await query.edit_message_text(f"🔍 **Analizando {ticker}...**\n⏳ **Calculando indicadores y sugerencias...**", parse_mode='Markdown')
        
        respuesta, _, _ = analizar_accion_completa(ticker)
        
        # Dividir respuesta si es muy larga
        if len(respuesta) > 4000:
            partes = [respuesta[i:i+4000] for i in range(0, len(respuesta), 4000)]
            for i, parte in enumerate(partes):
                if i == 0:
                    await query.edit_message_text(parte, parse_mode='Markdown')
                else:
                    await context.bot.send_message(chat_id=query.message.chat_id, text=parte, parse_mode='Markdown')
        else:
            await query.edit_message_text(respuesta, parse_mode='Markdown')
        
        # Mostrar menú después del análisis
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🎯 **¿Qué más quieres analizar?**\n👇 **Selecciona otra opción** 👇",
            reply_markup=crear_menu_principal(),
            parse_mode='Markdown'
        )
    
    elif query.data == "analizar_cualquier":
        # Este es el punto donde el bot pide el input
        await query.edit_message_text(
            """📝 **Escribe el símbolo de la acción que quieres analizar**

🔥 **EJEMPLOS:**
• **USA:** AAPL, TSLA, MSFT, GOOGL, AMZN
• **Argentina:** YPF, GGAL, BMA, PAMP

💡 **Tips:**
• Puedes escribir en minúsculas
• Para Argentina: YPF o YPF.BA
• Una acción por mensaje

🎯 **Escribe el ticker ahora:**""",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver al Menú", callback_data="menu")]])
        )
        context.user_data['modo'] = 'analizar_cualquier' # Se establece el modo para el siguiente mensaje
    
    elif query.data == "top_10_dia":
        await query.edit_message_text("📈 **Cargando Top 10 del Día...**\n⏳ **Esto puede tomar unos segundos...**", parse_mode='Markdown')
        await enviar_top_10_dia(update, context)
        # After sending the top 10, show the main menu again
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🎯 **¿Qué más quieres hacer?**\n👇 **Usa el menú para más opciones** 👇",
            reply_markup=crear_menu_principal(),
            parse_mode='Markdown'
        )

async def analizar_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = update.message.from_user
    
    # Registrar usuario si no existe
    if chat_id not in usuarios_registrados:
        registrar_usuario(
            chat_id=chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    
    ticker_input = str(update.message.text).strip()
    current_mode = context.user_data.get('modo')

    if current_mode == 'setup_manual':
        usuario_info = usuarios_registrados[chat_id]
        favoritas_usuario = usuario_info.get('acciones_favoritas', [])
        
        mensaje_busqueda = await update.message.reply_text(
            f"🔍 **Buscando '{ticker_input}'...**\n⏳ **Verificando en múltiples mercados...**",
            parse_mode='Markdown'
        )
        
        es_valido, ticker_encontrado, sugerencias = validar_ticker_con_sugerencias(ticker_input)
        
        if es_valido:
            if ticker_encontrado in favoritas_usuario:
                await mensaje_busqueda.edit_text(
                    f"⚠️ **{ticker_encontrado} ya está en tu lista**\n\n📋 **Favoritas actuales:** {', '.join(favoritas_usuario)}\n\n🎯 **Escribe otra acción:**",
                    parse_mode='Markdown'
                )
            else:
                favoritas_usuario.append(ticker_encontrado)
                usuarios_registrados[chat_id]['acciones_favoritas'] = favoritas_usuario
                guardar_usuarios()
                
                await mensaje_busqueda.edit_text(
                    f"✅ **{ticker_encontrado} agregada exitosamente**\n\n⭐ **Favoritas:** {len(favoritas_usuario)}\n📋 **Lista:** {', '.join(favoritas_usuario)}\n\n🎯 **Mínimo requerido:** 3",
                    parse_mode='Markdown'
                )
                
                if len(favoritas_usuario) >= 3:
                    usuarios_registrados[chat_id]['setup_completo'] = True # Mark setup as complete
                    guardar_usuarios()
                    context.user_data['modo'] = None # Clear mode
                    await update.message.reply_text(
                        f"🎉 **¡Ya tienes {len(favoritas_usuario)} favoritas!**\n\n✅ **Puedes finalizar el setup o agregar más**",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Finalizar Setup", callback_data="finalizar_setup")],
                            [InlineKeyboardButton("➕ Agregar Más", callback_data="setup_sugerencias")]
                        ]),
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        f"🎯 **Necesitas {3 - len(favoritas_usuario)} más**\n\n💡 **Escribe otra acción o usa el menú:**",
                        reply_markup=crear_menu_setup_inicial(),
                        parse_mode='Markdown'
                    )
        else:
            mensaje_error = f"❌ **No se encontraron datos para '{ticker_input}'**\n\n"
            if sugerencias:
                mensaje_error += f"💡 **¿Quisiste decir alguna de estas?**\n"
                for sugerencia in sugerencias:
                    mensaje_error += f"• {sugerencia}\n"
            else:
                mensaje_error += f"💡 **Verifica el símbolo e intenta de nuevo**\n\n"
            
            mensaje_error += f"🔥 **Ejemplos populares:**\n"
            mensaje_error += f"• **USA:** AAPL, TSLA, MSFT, GOOGL\n"
            mensaje_error += f"• **Argentina:** YPF, GGAL, BMA, PAMP\n\n"
            mensaje_error += f"💡 **Tips:**\n"
            mensaje_error += f"• Usa solo el símbolo (ej: AAPL)\n"
            mensaje_error += f"• Para Argentina puedes usar YPF o YPF.BA\n"
            mensaje_error += f"• Verifica la ortografía"
            
            await mensaje_busqueda.edit_text(mensaje_error, parse_mode='Markdown')
        
        # Keep mode if setup is not complete and ticker was invalid
        if not usuarios_registrados[chat_id].get('setup_completo', False) and not es_valido:
            context.user_data['modo'] = 'setup_manual'
        elif usuarios_registrados[chat_id].get('setup_completo', False):
            context.user_data['modo'] = None # Clear mode if setup is complete

    elif current_mode == 'analizar_cualquier':
        # Este es el punto donde se recibe el input del usuario para análisis
        mensaje_analisis = await update.message.reply_text(
            f"🔍 **Analizando '{ticker_input}'...**\n⏳ **Calculando indicadores y sugerencias...**", 
            parse_mode='Markdown'
        )
        
        es_valido, ticker_encontrado, sugerencias = validar_ticker_con_sugerencias(ticker_input)
        
        if es_valido:
            respuesta, _, _ = analizar_accion_completa(ticker_encontrado)
            await mensaje_analisis.edit_text(respuesta, parse_mode='Markdown')
        else:
            mensaje_error = f"❌ **No se encontraron datos para '{ticker_input}'**\n\n"
            if sugerencias:
                mensaje_error += f"💡 **¿Quisiste decir alguna de estas?**\n"
                for sugerencia in sugerencias:
                    mensaje_error += f"• {sugerencia}\n"
            mensaje_error += f"\n🔥 **Prueba con estos populares:**\n"
            mensaje_error += f"• AAPL, TSLA, MSFT, GOOGL, AMZN\n"
            mensaje_error += f"• YPF, GGAL, BMA, PAMP"
            await mensaje_analisis.edit_text(mensaje_error, parse_mode='Markdown')
        
        context.user_data['modo'] = None # Se limpia el modo después del análisis
        
        await update.message.reply_text(
            "🎯 **¿Qué más quieres hacer?**\n👇 **Usa el menú para más opciones** 👇",
            reply_markup=crear_menu_principal(),
            parse_mode='Markdown'
        )
    
    else: # Default behavior if no specific mode is set (e.g., user just types a ticker)
        # Check if setup is complete first
        if not usuarios_registrados[chat_id].get('setup_completo', False):
            await update.message.reply_text(
                f"⚠️ **CONFIGURACIÓN PENDIENTE**\n\n🎯 **Completa tu setup primero**",
                reply_markup=crear_menu_setup_inicial(),
                parse_mode='Markdown'
            )
            return

        mensaje_analisis = await update.message.reply_text(
            f"🔍 **Procesando '{ticker_input}'...**\n⏳ **Verificando y analizando...**",
            parse_mode='Markdown'
        )

        es_valido, ticker_encontrado, sugerencias = validar_ticker_con_sugerencias(ticker_input)

        if es_valido:
            usuario_info = usuarios_registrados[chat_id]
            favoritas_usuario = usuario_info.get('acciones_favoritas', [])

            if ticker_encontrado not in favoritas_usuario:
                favoritas_usuario.append(ticker_encontrado)
                usuarios_registrados[chat_id]['acciones_favoritas'] = favoritas_usuario
                guardar_usuarios()
                await mensaje_analisis.edit_text(
                    f"✅ **'{ticker_encontrado}' agregada a tus favoritas y analizando...**",
                    parse_mode='Markdown'
                )
            else:
                await mensaje_analisis.edit_text(
                    f"ℹ️ **'{ticker_encontrado}' ya está en tus favoritas. Analizando...**",
                    parse_mode='Markdown'
                )

            respuesta, _, _ = analizar_accion_completa(ticker_encontrado)
            # Send analysis as a new message to avoid editing the "added to favorites" message
            await context.bot.send_message(chat_id=chat_id, text=respuesta, parse_mode='Markdown')

        else:
            mensaje_error = f"❌ **No se encontraron datos para '{ticker_input}'**\n\n"
            if sugerencias:
                mensaje_error += f"💡 **¿Quisiste decir alguna de estas?**\n"
                for sugerencia in sugerencias:
                    mensaje_error += f"• {sugerencia}\n"
            mensaje_error += f"\n🔥 **Prueba con estos populares:**\n"
            mensaje_error += f"• AAPL, TSLA, MSFT, GOOGL, AMZN\n"
            mensaje_error += f"• YPF, GGAL, BMA, PAMP"
            await mensaje_analisis.edit_text(mensaje_error, parse_mode='Markdown')

        await update.message.reply_text(
            "🎯 **¿Qué más quieres hacer?**\n👇 **Usa el menú para más opciones** 👇",
            reply_markup=crear_menu_principal(),
            parse_mode='Markdown'
        )

async def enviar_alertas(context: ContextTypes.DEFAULT_TYPE):
    """Envía alertas inteligentes comparando TODAS las favoritas y recomendando la mejor"""
    usuarios_con_alertas = [
        chat_id for chat_id, info in usuarios_registrados.items() 
        if info.get('alertas_activas', True) and 
           info.get('setup_completo', False) and 
           len(info.get('acciones_favoritas', [])) >= 3
    ]
    
    if not usuarios_con_alertas:
        print("📭 No hay usuarios con alertas activas y setup completo")
        return
    
    print(f"🚨 Analizando favoritas de {len(usuarios_con_alertas)} usuarios...")
    
    for chat_id in usuarios_con_alertas:
        try:
            usuario_info = usuarios_registrados[chat_id]
            favoritas_usuario = usuario_info.get('acciones_favoritas', [])
            
            # Analizar TODAS las favoritas del usuario
            analisis_completo = []
            
            for ticker in favoritas_usuario:
                try:
                    respuesta, es_alerta, oportunidad = analizar_accion_completa(ticker)
                    
                    # Obtener datos adicionales para ranking
                    df, ticker_usado = obtener_datos_accion(ticker)
                    if df is not None:
                        precio_actual = float(df['Close'].iloc[-1])
                        precio_anterior = float(df['Close'].iloc[-2])
                        cambio_porcentaje = ((precio_actual - precio_anterior) / precio_anterior) * 100
                        
                        # Calcular score de oportunidad
                        score_oportunidad = 0
                        if oportunidad and oportunidad.get('es_oportunidad', False):
                            score_oportunidad = oportunidad.get('confianza', 0)
                        
                        analisis_completo.append({
                            'ticker': ticker_usado,
                            'precio': precio_actual,
                            'cambio_pct': cambio_porcentaje,
                            'es_oportunidad': oportunidad.get('es_oportunidad', False) if oportunidad else False,
                            'tipo_oportunidad': oportunidad.get('tipo', 'NINGUNA') if oportunidad else 'NINGUNA',
                            'confianza': score_oportunidad,
                            'razones': oportunidad.get('razon', []) if oportunidad else [],
                            'respuesta_completa': respuesta,
                            'es_alerta': es_alerta
                        })
                        
                except Exception as e:
                    print(f"❌ Error analizando {ticker}: {e}")
                    continue
            
            # Procesar y rankear oportunidades
            if analisis_completo:
                # Separar oportunidades reales de las que no lo son
                oportunidades_reales = [a for a in analisis_completo if a['es_oportunidad']]
                
                # Crear mensaje de resumen inteligente
                mensaje_resumen = crear_resumen_inteligente(analisis_completo, oportunidades_reales)
                
                # Solo enviar si hay contenido relevante
                if mensaje_resumen:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=mensaje_resumen,
                        parse_mode='Markdown'
                    )
                    
                    # Mostrar menú después de alerta
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="🎯 **¿Quieres análisis detallado de alguna?**",
                        reply_markup=crear_menu_principal(),
                        parse_mode='Markdown'
                    )
                    
                    print(f"🚨 Resumen inteligente enviado a {chat_id}")
                else:
                    print(f"📊 Sin oportunidades relevantes para {chat_id}")
                    
        except Exception as e:
            print(f"❌ Error procesando alertas para usuario {chat_id}: {e}")

def crear_resumen_inteligente(analisis_completo, oportunidades_reales):
    """Crea un resumen inteligente de todas las favoritas con recomendación"""
    try:
        if not analisis_completo:
            return None
        
        # Ordenar por confianza (mayor a menor)
        analisis_ordenado = sorted(analisis_completo, key=lambda x: x['confianza'], reverse=True)
        
        # Crear mensaje base
        mensaje = f"📊 **ANÁLISIS INTELIGENTE DE TUS {len(analisis_completo)} FAVORITAS** 📊\n"
        mensaje += f"{'='*50}\n"
        mensaje += f"🕐 **Análisis:** {datetime.now().strftime('%H:%M:%S')}\n\n"
        
        # Si hay oportunidades reales
        if oportunidades_reales:
            mejor_oportunidad = oportunidades_reales[0]  # Ya está ordenado por confianza
            
            mensaje += f"🎯 **MEJOR OPORTUNIDAD DETECTADA** 🎯\n"
            mensaje += f"🔥 **{mejor_oportunidad['ticker']}** - {mejor_oportunidad['tipo_oportunidad']}\n"
            mensaje += f"📈 **Confianza:** {mejor_oportunidad['confianza']}%\n"
            mensaje += f"💵 **Precio:** ${mejor_oportunidad['precio']:.2f}\n"
            
            if mejor_oportunidad['cambio_pct'] >= 0:
                mensaje += f"📈 **Cambio:** +{mejor_oportunidad['cambio_pct']:.2f}%\n"
            else:
                mensaje += f"📉 **Cambio:** {mejor_oportunidad['cambio_pct']:.2f}%\n"
            
            mensaje += f"\n🔍 **Razones clave:**\n"
            for razon in mejor_oportunidad['razones'][:3]:  # Solo las 3 principales
                mensaje += f"• {razon}\n"
            
            # Sugerencia personalizada
            if mejor_oportunidad['tipo_oportunidad'] == 'COMPRA':
                mensaje += f"\n💡 **MI RECOMENDACIÓN:**\n"
                mensaje += f"🟢 **Excelente momento para COMPRAR {mejor_oportunidad['ticker']}**\n"
                mensaje += f"🎯 **Entrada sugerida:** ${mejor_oportunidad['precio']:.2f}\n"
                mensaje += f"🛡️ **Stop Loss:** ${mejor_oportunidad['precio'] * 0.95:.2f} (-5%)\n"
                mensaje += f"🚀 **Objetivo:** ${mejor_oportunidad['precio'] * 1.10:.2f} (+10%)\n"
            else:
                mensaje += f"\n💡 **MI RECOMENDACIÓN:**\n"
                mensaje += f"🔴 **Momento para VENDER {mejor_oportunidad['ticker']}**\n"
                mensaje += f"🎯 **Precio actual:** ${mejor_oportunidad['precio']:.2f}\n"
                mensaje += f"📉 **Posible caída hasta:** ${mejor_oportunidad['precio'] * 0.90:.2f}\n"
            
            # Mostrar otras oportunidades si las hay
            otras_oportunidades = [o for o in oportunidades_reales[1:] if o['confianza'] >= 60]
            if otras_oportunidades:
                mensaje += f"\n🔥 **OTRAS OPORTUNIDADES:**\n"
                for oport in otras_oportunidades[:2]:  # Máximo 2 más
                    mensaje += f"• **{oport['ticker']}** ({oport['tipo_oportunidad']}) - {oport['confianza']}%\n"
        
        else:
            # No hay oportunidades, mostrar resumen general
            mensaje += f"📊 **RESUMEN GENERAL DE TUS FAVORITAS:**\n\n"
            
            # Mostrar las 3 mejores por performance
            mejores_performance = sorted(analisis_completo, key=lambda x: x['cambio_pct'], reverse=True)[:3]
            peores_performance = sorted(analisis_completo, key=lambda x: x['cambio_pct'])[:2]
            
            mensaje += f"🟢 **MEJORES DEL DÍA:**\n"
            for accion in mejores_performance:
                emoji = "📈" if accion['cambio_pct'] >= 0 else "📉"
                mensaje += f"{emoji} **{accion['ticker']}:** ${accion['precio']:.2f} ({accion['cambio_pct']:+.2f}%)\n"
            
            mensaje += f"\n🔴 **NECESITAN ATENCIÓN:**\n"
            for accion in peores_performance:
                mensaje += f"📉 **{accion['ticker']}:** ${accion['precio']:.2f} ({accion['cambio_pct']:+.2f}%)\n"
            
            mensaje += f"\n💡 **MI ANÁLISIS:**\n"
            mensaje += f"🟡 **Sin oportunidades de alta confianza ahora**\n"
            mensaje += f"⏳ **Recomiendo esperar mejores puntos de entrada**\n"
            mensaje += f"👀 **Mantente atento a las próximas alertas**\n"
        
        # Agregar estadísticas generales
        total_subiendo = len([a for a in analisis_completo if a['cambio_pct'] > 0])
        total_bajando = len([a for a in analisis_completo if a['cambio_pct'] < 0])
        
        mensaje += f"\n📊 **ESTADÍSTICAS:**\n"
        mensaje += f"🟢 **Subiendo:** {total_subiendo}/{len(analisis_completo)}\n"
        mensaje += f"🔴 **Bajando:** {total_bajando}/{len(analisis_completo)}\n"
        mensaje += f"🎯 **Oportunidades:** {len(oportunidades_reales)}\n"
        
        mensaje += f"\n⚠️ **Recuerda:** Este análisis es educativo, no consejo financiero\n"
        mensaje += f"🔄 **Próximo análisis:** En 15 minutos"
        
        return mensaje
        
    except Exception as e:
        print(f"❌ Error creando resumen inteligente: {e}")
        return None

def analizar_oportunidades_comparativas(analisis_completo):
    """Analiza y compara oportunidades para dar la mejor recomendación"""
    try:
        if not analisis_completo:
            return None
        
        # Calcular scores adicionales
        for analisis in analisis_completo:
            score_total = 0
            
            # Score por confianza de oportunidad
            if analisis['es_oportunidad']:
                score_total += analisis['confianza']
            
            # Score por momentum (cambio porcentual)
            if analisis['tipo_oportunidad'] == 'COMPRA':
                # Para compras, preferir acciones que han bajado (mejor precio)
                if analisis['cambio_pct'] < -2:
                    score_total += 20
                elif analisis['cambio_pct'] < 0:
                    score_total += 10
            else:
                # Para ventas, preferir acciones que han subido
                if analisis['cambio_pct'] > 2:
                    score_total += 20
                elif analisis['cambio_pct'] > 0:
                    score_total += 10
            
            # Score por número de razones técnicas
            score_total += len(analisis['razones']) * 5
            
            analisis['score_total'] = score_total
        
        # Ordenar por score total
        return sorted(analisis_completo, key=lambda x: x['score_total'], reverse=True)
        
    except Exception as e:
        print(f"❌ Error en análisis comparativo: {e}")
        return analisis_completo

# New function for Top 10
async def enviar_top_10_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obtiene y envía el Top 10 de acciones del día (USA y Argentina)"""
    
    # Curated list of popular and liquid stocks for Top 10
    # This list can be expanded or dynamically fetched from a source if available
    tickers_para_top_10 = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "JPM", # USA
        "YPF.BA", "GGAL.BA", "BMA.BA", "PAMP.BA", "TXAR.BA", "ALUA.BA", "CEPU.BA", "LOMA.BA", # Argentina
        "KO", "PEP", "V", "MA", "DIS", # More USA
        "BBAR.BA", "CEPU.BA", "EDN.BA", # More Argentina
    ]
    
    resultados_dia = []
    
    # Determine chat_id for sending messages
    chat_id = None
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
    elif update.message:
        chat_id = update.message.chat_id
    
    if not chat_id:
        print("❌ No se pudo determinar el chat_id para enviar el Top 10.")
        return

    # Send initial loading message
    message_to_edit = None
    if update.callback_query:
        message_to_edit = update.callback_query.message
    elif update.message:
        message_to_edit = update.message
    
    if message_to_edit:
        await message_to_edit.edit_text("📈 **Cargando Top 10 del Día...**\n⏳ **Esto puede tomar unos segundos...**", parse_mode='Markdown')

    for ticker in tickers_para_top_10:
        try:
            df, ticker_usado = obtener_datos_accion(ticker)
            if df is not None and len(df) >= 2:
                precio_actual = float(df['Close'].iloc[-1])
                precio_anterior = float(df['Close'].iloc[-2])
                if precio_anterior != 0:
                    cambio_porcentaje = ((precio_actual - precio_anterior) / precio_anterior) * 100
                    resultados_dia.append({
                        'ticker': ticker_usado,
                        'precio': precio_actual,
                        'cambio_pct': cambio_porcentaje
                    })
        except Exception as e:
            print(f"❌ Error obteniendo datos para Top 10 de {ticker}: {e}")
            continue
            
    if not resultados_dia:
        await context.bot.send_message(
            chat_id=chat_id, # Use chat_id directly
            text="❌ **No se pudieron obtener datos para el Top 10 del Día en este momento.**\n\n💡 **Intenta de nuevo más tarde.**",
            parse_mode='Markdown'
        )
        return

    # Ordenar por cambio porcentual (mayor a menor)
    top_10 = sorted(resultados_dia, key=lambda x: x['cambio_pct'], reverse=True)[:10]
    
    mensaje_top_10 = "📈 **TOP 10 ACCIONES DEL DÍA** 📈\n"
    mensaje_top_10 += f"{'='*40}\n"
    mensaje_top_10 += f"🕐 **Actualizado:** {datetime.now().strftime('%H:%M:%S')}\n\n"
    
    if top_10:
        for i, accion in enumerate(top_10, 1):
            emoji = "🟢" if accion['cambio_pct'] >= 0 else "🔴"
            mensaje_top_10 += f"{i}. {emoji} **{accion['ticker']}:** ${accion['precio']:.2f} ({accion['cambio_pct']:+.2f}%)\n"
    else:
        mensaje_top_10 += "No hay acciones disponibles para mostrar en el Top 10."
        
    mensaje_top_10 += f"\n⚠️ **Recuerda:** Este análisis es educativo, no consejo financiero."
    
    await context.bot.send_message(
        chat_id=chat_id, # Use chat_id directly
        text=mensaje_top_10,
        parse_mode='Markdown'
    )

# --- INICIO DEL BOT ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Cargar usuarios registrados al iniciar
    cargar_usuarios()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Manejadores de comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", lambda update, context: update.message.reply_text("Usa /start para comenzar")))
    
    # Manejador de botones
    app.add_handler(CallbackQueryHandler(manejar_botones))
    
    # Manejador de mensajes de texto
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analizar_manual))
    
    # Programador de alertas inteligentes
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: app.create_task(enviar_alertas(app.bot)),
        'interval',
        minutes=15
    )
    scheduler.start()
    
    print("🚀 Bot con ALERTAS INTELIGENTES activo...")
    print(f"👥 Usuarios registrados: {len(usuarios_registrados)}")
    print("🎯 Setup obligatorio para nuevos usuarios")
    print("🚨 Alertas inteligentes cada 15 minutos")
    print("💡 Sugerencias de trading personalizadas")
    print("🔥 Oportunidades de alta confianza")
    
    app.run_polling()
