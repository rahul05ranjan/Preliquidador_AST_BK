"""Configuración propia del módulo Facturación.

Vive en el módulo y no en `app/core/config.py` porque sólo la usa este módulo
(ADR-0013), como la de Preliquidación. Lee el mismo `.env` que el núcleo; los
dos declaran `extra="ignore"`, así que cada uno toma sus variables sin
rechazar las del otro.
"""
from datetime import date
from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Lo que acepta un Comprobante (plan de la E2, pregunta 12). El front repite
# los dos controles para avisar antes de subir (FB1).
TAMANO_MAXIMO = 10 * 1024 * 1024
MAXIMO_POR_COMPROBANTE = 5

# El Umbral y el Mes de corte mientras el Admin no los cambie (plan de la E3,
# decisión 4). Viven sólo acá: la tabla facturacion_configuracion nace vacía
# y el primer cambio crea su fila.
UMBRAL_INICIAL = Decimal("5.00")
MES_CORTE_INICIAL = date(2026, 10, 1)
# Cuántos meses puede pedir el Resumen de una vez (decisión 6).
MESES_MAXIMOS = 12
# El comentario de una Revisión de diferencia, como la columna (pregunta 15).
LARGO_COMENTARIO = 500


class ConfigFacturacion(BaseSettings):
    # Carpeta de los adjuntos (ADR-0019): una ruta absoluta del servidor,
    # fuera del código, porque el deploy reemplaza la carpeta del código
    # entera. Vacío = los adjuntos responden 503 en vez de frenar el arranque:
    # el resto de la app anda sin ellos.
    facturacion_adjuntos_dir: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


config = ConfigFacturacion()
