from django.db import models
from datetime import date
import cloudinary.utils
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from django_mongodb_backend.fields import (
    ArrayField,
    EmbeddedModelArrayField,
    EmbeddedModelField,
    ObjectIdField,
)
from django_mongodb_backend.models import EmbeddedModel
from django_mongodb_backend.constraints import EmbeddedFieldUniqueConstraint
from django_mongodb_backend.indexes import EmbeddedFieldIndex
from .validators import (
    calcular_edad,
    limpiar_espacios,
    normalizar_rut,
    normalizar_telefono_cl,
    validar_nombre_mostrar,
    validar_nombre_persona,
    validar_rut,
    validar_telefono_cl,
)

TIPO_CUENTA_CHOICES = [
    ("persona", "Persona natural"),
    ("entidad", "Entidad / empresa"),
]


# SUBDOCUMENTOS EMBEBIDOS

# --- Transversales ---
class Imagen(EmbeddedModel):
    """Imagen pública en Cloudinary (foto de perfil, portada)."""

    public_id = models.CharField(max_length=255)
    subido_en = models.DateTimeField(default=timezone.now)

    @property
    def url(self):
        return cloudinary.utils.cloudinary_url(self.public_id, secure=True)[0]


class DocumentoPrivado(EmbeddedModel):
    """Documento sensible en Cloudinary (type='authenticated'). Solo admins."""

    class TipoRecurso(models.TextChoices):
        IMAGEN = "image", "Imagen"
        ARCHIVO = "raw", "Archivo (PDF, etc.)"

    public_id = models.CharField(max_length=255)
    resource_type = models.CharField(
        max_length=10, choices=TipoRecurso.choices, default=TipoRecurso.IMAGEN
    )
    formato = models.CharField(max_length=10, blank=True)
    subido_en = models.DateTimeField(default=timezone.now)


class TaxonomiaRef(EmbeddedModel):
    """Referencia a una taxonomía con su nombre copiado (snapshot)."""

    taxonomia_id = ObjectIdField()
    nombre = models.CharField(max_length=100)


class Auditoria(EmbeddedModel):
    """Trazabilidad estándar de creación y modificación de registros."""

    creado_por = ObjectIdField(null=True, blank=True)
    creado_el = models.DateTimeField(default=timezone.now)
    actualizado_el = models.DateTimeField(default=timezone.now)


# --- De Usuario ---
class DatosPersona(EmbeddedModel):
    nombres = models.CharField(max_length=100, validators=[validar_nombre_persona])
    apellidos = models.CharField(max_length=100, validators=[validar_nombre_persona])
    fecha_nacimiento = models.DateField()
    habilidades = EmbeddedModelArrayField(TaxonomiaRef, default=list, blank=True)


class DatosEntidad(EmbeddedModel):
    razon_social = models.CharField(max_length=200, validators=[validar_nombre_mostrar])
    fecha_creacion = models.DateField()


class DocumentosVerificacion(EmbeddedModel):
    erut = EmbeddedModelField(DocumentoPrivado, null=True, blank=True)
    representacion_legal = EmbeddedModelField(DocumentoPrivado, null=True, blank=True)
    cedula_anverso = EmbeddedModelField(DocumentoPrivado, null=True, blank=True)
    cedula_reverso = EmbeddedModelField(DocumentoPrivado, null=True, blank=True)


class RevisionAdmin(EmbeddedModel):
    admin_id = ObjectIdField()
    fecha = models.DateTimeField(default=timezone.now)
    observacion = models.TextField(blank=True)


class VerificacionPublicador(EmbeddedModel):
    """Solo existe cuando un cliente solicita poder organizar actividades."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"

    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    rut = models.CharField(max_length=12, null=True, blank=True)
    documentos = EmbeddedModelField(DocumentosVerificacion)
    revision_admin = EmbeddedModelField(RevisionAdmin, null=True, blank=True)
    fecha_solicitud = models.DateTimeField(default=timezone.now)


# --- De Actividad ---
class Creador(EmbeddedModel):
    usuario_id = ObjectIdField()
    nombre_mostrar = models.CharField(max_length=100)
    tipo_cuenta = models.CharField(max_length=10, choices=TIPO_CUENTA_CHOICES)


class Clasificacion(EmbeddedModel):
    categoria = EmbeddedModelField(TaxonomiaRef)
    nivel_esfuerzo = EmbeddedModelField(TaxonomiaRef)
    accesibilidad = EmbeddedModelArrayField(TaxonomiaRef, default=list, blank=True)


class Horario(EmbeddedModel):
    inicio = models.DateTimeField()
    fin = models.DateTimeField()
    duracion_minutos = models.PositiveIntegerField(default=0, editable=False)


class Cupos(EmbeddedModel):
    total = models.PositiveIntegerField()
    disponible = models.PositiveIntegerField(null=True, blank=True)


class Costo(EmbeddedModel):
    monto = models.PositiveIntegerField(default=0, help_text="CLP. 0 = gratuita.")

    @property
    def es_gratuito(self):
        return self.monto == 0


class PuntoGeoJSON(EmbeddedModel):
    """GeoJSON Point. El orden de coordinates es [longitud, latitud]."""

    type = models.CharField(max_length=5, default="Point", editable=False)
    coordinates = ArrayField(models.FloatField(), size=2)


class Ubicacion(EmbeddedModel):
    comuna = models.CharField(max_length=100)
    direccion_privada = models.CharField(max_length=255)
    geo_exacta = EmbeddedModelField(PuntoGeoJSON)


class Moderacion(EmbeddedModel):
    bloqueado_por_admin_id = ObjectIdField()
    motivo = models.TextField()
    fecha_bloqueo = models.DateTimeField(default=timezone.now)


# --- De Inscripción ---
class ActividadResumen(EmbeddedModel):
    titulo = models.CharField(max_length=150)
    fecha_inicio = models.DateTimeField()
    comuna = models.CharField(max_length=100, blank=True)
    imagen_portada_public_id = models.CharField(max_length=255, blank=True)


class ParticipanteResumen(EmbeddedModel):
    nombre_mostrar = models.CharField(max_length=100)
    correo = models.EmailField()
    telefono = models.CharField(max_length=20, blank=True)


class AuditoriaInscripcion(EmbeddedModel):
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    dispositivo = models.CharField(max_length=255, blank=True)


# --- De Reporte ---
class Reportante(EmbeddedModel):
    usuario_id = ObjectIdField()
    nombre_mostrar = models.CharField(max_length=100)


class ObjetivoReporte(EmbeddedModel):
    class Tipo(models.TextChoices):
        ACTIVIDAD = "actividad", "Actividad"
        USUARIO = "usuario", "Usuario"
        MENSAJE_CHAT = "mensaje_chat", "Mensaje de chat"

    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    elemento_id = models.CharField(max_length=128)
    actividad_id = ObjectIdField(null=True, blank=True)
    snapshot_contenido = models.TextField(blank=True)


class ResolucionAdmin(EmbeddedModel):
    class Accion(models.TextChoices):
        SIN_ACCION = "sin_accion", "Sin acción"
        ADVERTENCIA = "advertencia", "Advertencia"
        CONTENIDO_OCULTADO = "contenido_ocultado", "Contenido ocultado"
        ACTIVIDAD_BLOQUEADA = "actividad_bloqueada", "Actividad bloqueada"
        CUENTA_SUSPENDIDA = "cuenta_suspendida", "Cuenta suspendida"

    admin_id = ObjectIdField()
    accion_tomada = models.CharField(max_length=20, choices=Accion.choices)
    fecha_resolucion = models.DateTimeField(default=timezone.now)


# 2. COLECCIONES PRINCIPALES

# --- Taxonomia ---
class Taxonomia(models.Model):
    class Tipo(models.TextChoices):
        CATEGORIA = "categoria", "Categoría de actividad"
        NIVEL_ESFUERZO = "nivel_esfuerzo", "Nivel de esfuerzo"
        ACCESIBILIDAD = "accesibilidad", "Accesibilidad"
        HABILIDAD = "habilidad", "Habilidad de usuario"
        MOTIVO_REPORTE = "motivo_reporte", "Motivo de reporte"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)
    auditoria = EmbeddedModelField(Auditoria, default=Auditoria)

    class Meta:
        db_table = "taxonomias"
        constraints = [
            models.UniqueConstraint(fields=["tipo", "slug"], name="uniq_taxonomia_tipo_slug"),
        ]
        indexes = [
            models.Index(fields=["tipo", "activa"], name="idx_tax_tipo_activa"),
        ]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        campos = set(update_fields) if update_fields is not None else None

        if campos is None or "nombre" in campos:
            self.nombre = limpiar_espacios(self.nombre)

        if not self.slug:
            self.slug = slugify(self.nombre)
            if campos is not None:
                campos.add("slug")

        self.auditoria.actualizado_el = timezone.now()
        if campos is not None:
            campos.add("auditoria")
            kwargs["update_fields"] = campos
        else:
            self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.nombre}"


# --- Usuario ---
class Usuario(models.Model):
    class TipoCuenta(models.TextChoices):
        PERSONA = "persona", "Persona natural"
        ENTIDAD = "entidad", "Entidad / empresa"

    class Rol(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        PUBLICADOR = "publicador", "Publicador"
        ADMIN = "admin", "Administrador"

    firebase_uid = models.CharField(max_length=128, unique=True)
    correo = models.EmailField(unique=True)
    tipo_cuenta = models.CharField(max_length=10, choices=TipoCuenta.choices)
    rol = models.CharField(max_length=12, choices=Rol.choices, default=Rol.CLIENTE)
    nombre_mostrar = models.CharField(max_length=100, validators=[validar_nombre_mostrar])
    biografia = models.TextField(blank=True)
    telefono = models.CharField(max_length=20, blank=True, validators=[validar_telefono_cl])
    foto_perfil = EmbeddedModelField(Imagen, null=True, blank=True)

    datos_persona = EmbeddedModelField(DatosPersona, null=True, blank=True)
    datos_entidad = EmbeddedModelField(DatosEntidad, null=True, blank=True)

    verificacion_publicador = EmbeddedModelField(
        VerificacionPublicador, null=True, blank=True
    )

    actividades_favoritas = ArrayField(ObjectIdField(), default=list, blank=True)
    is_active = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "usuarios"
        constraints = []
        indexes = [
            models.Index(fields=["rol", "is_active"], name="idx_usr_rol_activo"),
            EmbeddedFieldIndex(
                fields=["verificacion_publicador.estado"],
                name="idx_usr_verif_estado",
            ),
        ]

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def es_admin(self):
        return self.rol == self.Rol.ADMIN

    @property
    def es_publicador(self):
        return self.rol in (self.Rol.PUBLICADOR, self.Rol.ADMIN)

    def clean(self):
        errores = {}

        if self.tipo_cuenta == self.TipoCuenta.PERSONA:
            if not self.datos_persona:
                errores["datos_persona"] = "Requerido para personas naturales."
            else:
                try:
                    edad = calcular_edad(self.datos_persona.fecha_nacimiento)
                    if edad is not None and edad < 18:
                        errores["datos_persona"] = "Debes ser mayor de 18 años para registrarte."
                except ValidationError as exc:
                    errores["datos_persona"] = exc.messages
            if self.datos_entidad:
                errores["datos_entidad"] = "No corresponde a una persona natural."

        elif self.tipo_cuenta == self.TipoCuenta.ENTIDAD:
            if not self.datos_entidad:
                errores["datos_entidad"] = "Requerido para entidades."
            elif self.datos_entidad.fecha_creacion > date.today():
                errores["datos_entidad"] = "La fecha de creación no puede ser futura."
            if self.datos_persona:
                errores["datos_persona"] = "No corresponde a una entidad."

        verificacion = self.verificacion_publicador
        if verificacion:
            verificacion.rut = normalizar_rut(verificacion.rut)
            if verificacion.rut:
                try:
                    validar_rut(verificacion.rut)
                except ValidationError as exc:
                    errores["verificacion_publicador"] = exc.messages

        if self.rol == self.Rol.PUBLICADOR:
            if (
                not verificacion
                or verificacion.estado != VerificacionPublicador.Estado.APROBADA
                or not verificacion.rut
            ):
                errores["rol"] = "Un publicador requiere verificación aprobada y RUT."

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        campos = set(update_fields) if update_fields is not None else None

        if campos is None or "correo" in campos:
            self.correo = self.correo.strip().lower()
        if campos is None or "nombre_mostrar" in campos:
            self.nombre_mostrar = limpiar_espacios(self.nombre_mostrar)
        if campos is None or "telefono" in campos:
            self.telefono = normalizar_telefono_cl(self.telefono) or ""

        if (campos is None or "datos_persona" in campos) and self.datos_persona:
            self.datos_persona.nombres = limpiar_espacios(self.datos_persona.nombres)
            self.datos_persona.apellidos = limpiar_espacios(self.datos_persona.apellidos)
        if (campos is None or "datos_entidad" in campos) and self.datos_entidad:
            self.datos_entidad.razon_social = limpiar_espacios(self.datos_entidad.razon_social)
        if (campos is None or "verificacion_publicador" in campos) and self.verificacion_publicador:
            self.verificacion_publicador.rut = (
                normalizar_rut(self.verificacion_publicador.rut) or None
            )

        if campos is None:
            self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre_mostrar} <{self.correo}>"


# --- Actividad ---
class Actividad(models.Model):
    class Modalidad(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        ONLINE = "online", "Online"
        MIXTA = "mixta", "Mixta"

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        PUBLICADA = "publicada", "Publicada"
        FINALIZADA = "finalizada", "Finalizada"
        CANCELADA = "cancelada", "Cancelada"
        BLOQUEADA = "bloqueada", "Bloqueada por moderación"

    titulo = models.CharField(max_length=150)
    descripcion = models.TextField()
    modalidad = models.CharField(max_length=12, choices=Modalidad.choices)
    imagen_portada = EmbeddedModelField(Imagen, null=True, blank=True)
    creador = EmbeddedModelField(Creador)
    clasificacion = EmbeddedModelField(Clasificacion)
    horario = EmbeddedModelField(Horario)
    cupos = EmbeddedModelField(Cupos)
    costo = EmbeddedModelField(Costo, default=Costo)
    ubicacion = EmbeddedModelField(Ubicacion, null=True, blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)
    moderacion = EmbeddedModelField(Moderacion, null=True, blank=True)
    auditoria = EmbeddedModelField(Auditoria, default=Auditoria)

    class Meta:
        db_table = "actividades"
        indexes = [
            EmbeddedFieldIndex(
                fields=["estado", "horario.inicio"],
                name="idx_act_estado_inicio",
            ),
            EmbeddedFieldIndex(
                fields=["ubicacion.comuna"],
                name="idx_act_comuna",
            ),
            EmbeddedFieldIndex(
                fields=["clasificacion.categoria.taxonomia_id"],
                name="idx_act_categoria",
            ),
            EmbeddedFieldIndex(
                fields=["creador.usuario_id"],
                name="idx_act_creador",
            ),
        ]

    def clean(self):
        errores = {}

        if self.horario and self.horario.inicio and self.horario.fin:
            if self.horario.fin <= self.horario.inicio:
                errores["horario"] = "El término debe ser posterior al inicio."

        if self.cupos:
            if self.cupos.total < 1:
                errores["cupos"] = "La actividad debe tener al menos 1 cupo."
            elif (
                self.cupos.disponible is not None
                and self.cupos.disponible > self.cupos.total
            ):
                errores["cupos"] = "Los cupos disponibles no pueden superar el total."

        if self.modalidad in (self.Modalidad.PRESENCIAL, self.Modalidad.MIXTA):
            if not self.ubicacion:
                errores["ubicacion"] = "Requerida para actividades presenciales o mixtas."
            elif (
                not self.ubicacion.geo_exacta
                or not self.ubicacion.geo_exacta.coordinates
                or len(self.ubicacion.geo_exacta.coordinates) != 2
            ):
                errores["ubicacion"] = "Coordenadas geográficas requeridas en formato [lng, lat]."
            else:
                lng, lat = self.ubicacion.geo_exacta.coordinates
                if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                    errores["ubicacion"] = "Coordenadas fuera de rango ([lng, lat])."

        if self.estado == self.Estado.BLOQUEADA and not self.moderacion:
            errores["moderacion"] = "Una actividad bloqueada requiere datos de moderación."

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        campos = set(update_fields) if update_fields is not None else None

        if campos is None or "titulo" in campos:
            self.titulo = limpiar_espacios(self.titulo)
        if (campos is None or "ubicacion" in campos) and self.ubicacion:
            self.ubicacion.comuna = limpiar_espacios(self.ubicacion.comuna)
            self.ubicacion.direccion_privada = limpiar_espacios(self.ubicacion.direccion_privada)
        if (campos is None or "horario" in campos) and self.horario and self.horario.inicio and self.horario.fin:
            delta = self.horario.fin - self.horario.inicio
            self.horario.duracion_minutos = max(int(delta.total_seconds() // 60), 0)
        if (campos is None or "cupos" in campos) and self.cupos and self.cupos.disponible is None:
            self.cupos.disponible = self.cupos.total

        self.auditoria.actualizado_el = timezone.now()
        if campos is not None:
            campos.add("auditoria")
            kwargs["update_fields"] = campos
        else:
            self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo


# --- Inscripcion ---
class Inscripcion(models.Model):
    class Estado(models.TextChoices):
        CONFIRMADA = "confirmada", "Confirmada"
        CANCELADA = "cancelada", "Cancelada"

    actividad = models.ForeignKey(
        Actividad, on_delete=models.PROTECT, related_name="inscripciones"
    )
    usuario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name="inscripciones"
    )
    actividad_resumen = EmbeddedModelField(ActividadResumen)
    participante_resumen = EmbeddedModelField(ParticipanteResumen)
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.CONFIRMADA
    )
    fecha_inscripcion = models.DateTimeField(default=timezone.now)
    fecha_cancelacion = models.DateTimeField(null=True, blank=True)
    auditoria = EmbeddedModelField(AuditoriaInscripcion, null=True, blank=True)

    class Meta:
        db_table = "inscripciones"
        constraints = [
            models.UniqueConstraint(fields=["actividad", "usuario"], name="uniq_inscripcion"),
        ]
        indexes = [
            models.Index(fields=["usuario", "estado"], name="idx_insc_usuario_estado"),
            models.Index(fields=["actividad", "estado"], name="idx_insc_actividad_estado"),
        ]

    def clean(self):
        if self.estado == self.Estado.CANCELADA and not self.fecha_cancelacion:
            self.fecha_cancelacion = timezone.now()
        elif self.estado == self.Estado.CONFIRMADA:
            self.fecha_cancelacion = None

    def save(self, *args, **kwargs):
        if self.estado == self.Estado.CANCELADA and not self.fecha_cancelacion:
            self.fecha_cancelacion = timezone.now()
        elif self.estado == self.Estado.CONFIRMADA:
            self.fecha_cancelacion = None

        if kwargs.get("update_fields") is None:
            self.full_clean()

        super().save(*args, **kwargs)


# --- Reporte ---
class Reporte(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EN_REVISION = "en_revision", "En revisión"
        RESUELTO = "resuelto", "Resuelto"
        DESCARTADO = "descartado", "Descartado"

    reportante = EmbeddedModelField(Reportante)
    objetivo = EmbeddedModelField(ObjetivoReporte)
    motivo = EmbeddedModelArrayField(TaxonomiaRef)
    detalle_usuario = models.TextField(blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    resolucion_admin = EmbeddedModelField(ResolucionAdmin, null=True, blank=True)
    fecha_reporte = models.DateTimeField(default=timezone.now)
    huella = models.CharField(max_length=200, unique=True, editable=False)

    class Meta:
        db_table = "reportes"
        indexes = [
            models.Index(fields=["estado", "fecha_reporte"], name="idx_rep_estado_fecha"),
            EmbeddedFieldIndex(
                fields=["objetivo.tipo", "objetivo.elemento_id"],
                name="idx_rep_objetivo",
            ),
        ]

    def clean(self):
        if (
            self.objetivo
            and self.objetivo.tipo == ObjetivoReporte.Tipo.MENSAJE_CHAT
            and not self.objetivo.actividad_id
        ):
            raise ValidationError(
                {"objetivo": "Los reportes de mensajes de chat deben incluir actividad_id."}
            )

        if self.estado in (self.Estado.RESUELTO, self.Estado.DESCARTADO) and not self.resolucion_admin:
            raise ValidationError(
                {"resolucion_admin": "Debes registrar la resolución administrativa."}
            )

    def save(self, *args, **kwargs):
        if not self.huella:
            self.huella = (
                f"{self.reportante.usuario_id}:{self.objetivo.tipo}:{self.objetivo.elemento_id}"
            )

        if kwargs.get("update_fields") is None:
            self.full_clean()

        super().save(*args, **kwargs)