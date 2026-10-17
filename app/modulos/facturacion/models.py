"""Modelos SQLAlchemy del módulo Facturación.

Espejo de las migraciones de `migrations/facturacion/`. **La fuente de verdad
del esquema son ellas, no esto** (regla 9 de GUIA-MODULOS): acá se declara lo
mismo para que el ORM pueda leer y escribir, y para que el chequeo de tablas
faltantes del arranque cubra al módulo.

La tabla de la E1 se borró con `facturacion/002`, porque la Unidad sugerida se
lee del sistema de campo. Las de acá son de la E2 (`facturacion/003`): el
Comprobante, sus Líneas y sus Adjuntos; y de la E3 (`facturacion/004`): la
configuración del Resumen y la Revisión de diferencia, que la `facturacion/006`
pasó a grupos de tareas con su período.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric,
    SmallInteger, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
# Usuario vive en el núcleo. Se importa acá a propósito: `creado_por`,
# `actualizado_por`, `subido_por` y los de la Revisión tienen ForeignKey("usuarios.id"), que
# SQLAlchemy resuelve por nombre, así que importar este módulo tiene que
# registrar Usuario primero. No borrar.
from app.core.models import Usuario, ahora_utc  # noqa: F401


class Comprobante(Base):
    """Una Factura o Nota de crédito emitida a un Cliente (003).

    Se carga a mano o llega de la migración del histórico (`es_historico`). El
    Cliente y la Empresa son copias al guardar: el listado no lee la base de
    campo. Empresa, número y fecha sólo pueden quedar vacíos en un histórico.

    `clave_identidad` la calcula el servicio (`reglas_comprobante.clave_identidad`)
    y la base la hace cumplir. Existe porque el histórico no tiene Empresa,
    MySQL acepta varios NULL en un UNIQUE y en la planilla el mismo número
    aparece para dos Clientes; de ella depende el "sin duplicar" de la
    migración del histórico.
    """
    __tablename__ = "facturacion_comprobante"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    # `factura` o `nota_credito` (reglas_comprobante.TIPOS).
    tipo                  = Column(String(20), nullable=False)
    # El id del maestro de clientes del sistema de campo.
    cliente_id            = Column(Integer, nullable=False)
    cliente_nombre        = Column(String(150), nullable=False)
    empresa_emisora       = Column(String(100), nullable=True)
    # Normalizado. Vacío sólo en un histórico sin número.
    numero                = Column(String(30), nullable=True)
    fecha                 = Column(Date, nullable=True)
    # Obligatoria en una Nota de crédito cargada a mano. La FK no tiene ON
    # DELETE: la base no deja borrar una Factura que tiene Notas de crédito.
    factura_corregida_id  = Column(Integer, ForeignKey("facturacion_comprobante.id"), nullable=True)
    es_historico          = Column(Boolean, nullable=False, default=False)
    # Sólo en un histórico sin número posterior al corte: el Cruce (E3) no
    # cuenta sus Líneas como facturado.
    pendiente_de_facturar = Column(Boolean, nullable=False, default=False)
    clave_identidad       = Column(String(160), nullable=False)
    creado_en             = Column(DateTime, nullable=False, default=ahora_utc)
    # NULL = lo creó la migración del histórico, no una persona.
    creado_por            = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    # NULL = nunca se editó. Lo sella el servicio al editar, no un onupdate:
    # el reemplazo de un histórico por el script no es una edición.
    actualizado_en        = Column(DateTime, nullable=True)
    actualizado_por       = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    # El PUT reemplaza todas las Líneas: las que salen de la lista se borran.
    lineas = relationship(
        "LineaComprobante", back_populates="comprobante",
        cascade="all, delete-orphan", order_by="LineaComprobante.orden",
    )
    # Sin cascada a propósito: los Adjuntos los borra el servicio junto con sus
    # archivos. Borrar directo un Comprobante con Adjuntos falla (la FK es NOT
    # NULL), que es lo que se quiere.
    adjuntos = relationship("Adjunto", back_populates="comprobante", order_by="Adjunto.id")
    # Sólo el lado de la Nota de crédito. Sin la colección inversa a propósito:
    # con ella, borrar una Factura desde el ORM pondría en NULL la referencia
    # de sus Notas en vez de dejar que la base lo frene.
    factura_corregida = relationship("Comprobante", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("clave_identidad", name="uq_facturacion_comprobante_clave"),
        Index("ix_facturacion_comprobante_cliente_numero", "cliente_id", "numero"),
        Index("ix_facturacion_comprobante_fecha", "fecha"),
    )


class LineaComprobante(Base):
    """Una Línea de un Comprobante: qué tarea, cuánto y a qué precio (003).

    El importe es siempre >= 0; el signo lo da el tipo del Comprobante, como en
    Terceros. En una Línea cargada a mano lo calcula el backend
    (`reglas_comprobante.calcular_importe`); en un histórico es el de la
    planilla, tal cual.
    """
    __tablename__ = "facturacion_linea"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    # En la base, ON DELETE CASCADE: el DELETE de vuelta atrás de los
    # históricos se lleva sus Líneas.
    comprobante_id  = Column(
        Integer, ForeignKey("facturacion_comprobante.id", ondelete="CASCADE"), nullable=False,
    )
    orden           = Column(SmallInteger, nullable=False)
    # La fecha a facturar (el 1 o el 16), no la del Comprobante.
    fecha           = Column(Date, nullable=False)
    tarea_id        = Column(Integer, nullable=False)
    # Copia del maestro al guardar.
    tarea_nombre    = Column(String(150), nullable=False)
    # Una de las nueve claves de app/modulos/facturacion/unidades.py.
    unidad          = Column(String(20), nullable=False)
    # Las dos o ninguna.
    finca_id        = Column(Integer, nullable=True)
    finca_nombre    = Column(String(150), nullable=True)
    cantidad        = Column(Numeric(14, 2), nullable=False)
    precio_unitario = Column(Numeric(14, 4), nullable=False)
    importe         = Column(Numeric(14, 2), nullable=False)

    comprobante = relationship("Comprobante", back_populates="lineas")

    __table_args__ = (
        Index("ix_facturacion_linea_comprobante", "comprobante_id"),
        # Para el Cruce de la E3, que busca por tarea y fecha.
        Index("ix_facturacion_linea_tarea_fecha", "tarea_id", "fecha"),
    )


class Adjunto(Base):
    """Un PDF o una imagen de un Comprobante, guardado en la carpeta de
    adjuntos del VPS (003, ADR-0019).

    El nombre en disco lo genera el sistema (`uuid4().hex` y la extensión del
    tipo detectado); el del usuario sólo se guarda saneado, para mostrar. El
    tipo es el detectado por contenido, nunca el que declaró el navegador.
    """
    __tablename__ = "facturacion_adjunto"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    # Sin cascada, ni en la base ni en la relación: ver Comprobante.adjuntos.
    comprobante_id  = Column(Integer, ForeignKey("facturacion_comprobante.id"), nullable=False)
    nombre_original = Column(String(255), nullable=False)
    nombre_en_disco = Column(String(64), nullable=False)
    tipo_contenido  = Column(String(50), nullable=False)
    tamano_bytes    = Column(Integer, nullable=False)
    subido_en       = Column(DateTime, nullable=False, default=ahora_utc)
    subido_por      = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    comprobante = relationship("Comprobante", back_populates="adjuntos")

    __table_args__ = (
        UniqueConstraint("nombre_en_disco", name="uq_facturacion_adjunto_nombre_en_disco"),
    )


class Configuracion(Base):
    """El Umbral y el Mes de corte del Resumen (004). Una sola fila, la de id 1.

    Nace vacía: sin fila, el servicio usa los valores iniciales de `config.py`,
    y el primer cambio del Admin la crea. Así los valores iniciales viven en un
    solo lugar (plan de la E3, decisión 4).
    """
    __tablename__ = "facturacion_configuracion"

    # Siempre 1: sin autoincremento a propósito.
    id              = Column(Integer, primary_key=True, autoincrement=False)
    # Porcentaje: 5.00 es 5 %.
    umbral_pct      = Column(Numeric(5, 2), nullable=False)
    # El día 1 del mes de corte.
    mes_corte       = Column(Date, nullable=False)
    actualizado_en  = Column(DateTime, nullable=False, default=ahora_utc)
    actualizado_por = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)


class RevisionDiferencia(Base):
    """La Revisión de diferencia de un Cliente en un mes y un período (004 y 006).

    Guarda el comentario, quién y cuándo, el período en que se dejó (`desde` y
    `hasta`, dentro del mes) y en `grupos` las (grupo, unidad) que superaban el
    Umbral cuando se dejó. No se borra al deshacerla: se sellan `deshecha_en` y
    `deshecha_por`, y queda en el registro. La vigente es la más reciente del
    (Cliente, mes, período exacto) que no fue deshecha.
    """
    __tablename__ = "facturacion_revision"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    # El id del maestro de clientes del sistema de campo.
    cliente_id   = Column(Integer, nullable=False)
    # El día 1 del mes.
    mes          = Column(Date, nullable=False)
    # El período revisado, los dos días incluidos y dentro del mes. Las
    # Revisiones anteriores a la 006 quedaron con el mes entero.
    desde        = Column(Date, nullable=False)
    hasta        = Column(Date, nullable=False)
    comentario   = Column(String(500), nullable=False)
    creada_en    = Column(DateTime, nullable=False, default=ahora_utc)
    creada_por   = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    # NULL = vigente, nadie la deshizo.
    deshecha_en  = Column(DateTime, nullable=True)
    deshecha_por = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    grupos = relationship(
        "RevisionGrupo", back_populates="revision",
        cascade="all, delete-orphan", order_by="RevisionGrupo.id",
    )

    __table_args__ = (
        # No único: se guardan todas, también las deshechas.
        Index("ix_facturacion_revision_cliente_mes_periodo",
              "cliente_id", "mes", "desde", "hasta"),
    )


class RevisionGrupo(Base):
    """Una (grupo de tareas, unidad) que superaba cuando se dejó la Revisión (006)."""
    __tablename__ = "facturacion_revision_grupo"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    # En la base, ON DELETE CASCADE: los grupos caen con su Revisión.
    revision_id = Column(
        Integer, ForeignKey("facturacion_revision.id", ondelete="CASCADE"), nullable=False,
    )
    # El grupo de tareas del maestro del campo, como se leyó. NULL = Sin grupo.
    grupo       = Column(String(255), nullable=True)
    # Una de las claves de unidades.py, como LineaComprobante.unidad. NULL = la
    # línea no tenía unidad (tareas sin facturado y sin Unidad sugerida).
    unidad      = Column(String(20), nullable=True)

    revision = relationship("RevisionDiferencia", back_populates="grupos")

    __table_args__ = (
        Index("ix_facturacion_revision_grupo_revision", "revision_id"),
    )
