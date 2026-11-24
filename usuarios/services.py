import json
import logging
import os
import time
from functools import lru_cache
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import firebase_admin
from django.conf import settings
from django.db import connections, router, transaction
from django.utils import timezone
from firebase_admin import auth as fb_auth
from firebase_admin import credentials as fb_credentials
from firebase_admin import firestore as fb_firestore
from firebase_admin.exceptions import FirebaseError
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId
from .models import (
    Actividad,
    ActividadResumen,
    AuditoriaInscripcion,
    DocumentoPrivado,
    Imagen,
    Inscripcion,
    ParticipanteResumen,
    Usuario,
)

logger = logging.getLogger(__name__)

_MAX_REINTENTOS = 3

_TAMANO_MAX_IMAGEN = 5 * 1024 * 1024
_TAMANO_MAX_DOCUMENTO = 10 * 1024 * 1024
_TIPOS_IMAGEN = {"image/jpeg", "image/png", "image/webp"}
_TIPOS_DOCUMENTO = _TIPOS_IMAGEN | {"application/pdf"}
_EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp"}
_EXTENSIONES_DOCUMENTO = _EXTENSIONES_IMAGEN | {".pdf"}
_FORMATOS_CLOUDINARY_DOC = ["jpg", "jpeg", "png", "webp", "pdf"]


# Errores de negocio
class ErrorServicio(Exception):
    """Base de errores esperables; la vista los traduce a respuestas 4xx."""


class TokenFirebaseInvalido(ErrorServicio):
    """El ID token de Firebase es inválido, expiró o fue revocado."""


class ActividadNoDisponible(ErrorServicio):
    pass


class SinCupos(ErrorServicio):
    pass


class YaInscrito(ErrorServicio):
    pass


class InscripcionNoEncontrada(ErrorServicio):
    pass


class ArchivoInvalido(ErrorServicio):
    pass


# FIREBASE ADMIN & CLOUD FIRESTORE
@lru_cache(maxsize=1)
def _obtener_credenciales():
    cred_dict = getattr(settings, "FIREBASE_CREDENTIALS_DICT", None)
    if isinstance(cred_dict, dict) and cred_dict:
        return fb_credentials.Certificate(cred_dict)

    cred_json = getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")
    if cred_json:
        parsed = json.loads(cred_json) if isinstance(cred_json, str) else cred_json
        return fb_credentials.Certificate(parsed)

    cred_file = getattr(settings, "FIREBASE_CREDENTIALS_FILE", "") or getattr(
        settings, "FIREBASE_CREDENTIALS_PATH", ""
    )
    if cred_file:
        return fb_credentials.Certificate(str(cred_file))

    return fb_credentials.ApplicationDefault()


@lru_cache(maxsize=1)
def _firebase_app() -> firebase_admin.App:
    if firebase_admin._apps:
        return firebase_admin.get_app()

    cred = _obtener_credenciales()
    options = {}
    project_id = getattr(settings, "FIREBASE_PROJECT_ID", "")
    if project_id:
        options["projectId"] = project_id

    return firebase_admin.initialize_app(cred, options or None)


def verificar_token(token: str) -> dict:
    """Devuelve el payload decodificado del ID token o lanza TokenFirebaseInvalido."""
    app = _firebase_app()
    clock_skew = getattr(settings, "FIREBASE_AUTH_CLOCK_SKEW_SECONDS", 10)
    check_revoked = getattr(settings, "FIREBASE_AUTH_CHECK_REVOKED", False)

    try:
        return fb_auth.verify_id_token(
            token,
            app=app,
            check_revoked=check_revoked,
            clock_skew_seconds=clock_skew,
        )
    except fb_auth.RevokedIdTokenError as exc:
        raise TokenFirebaseInvalido("El token ha sido revocado. Inicia sesión nuevamente.") from exc
    except fb_auth.ExpiredIdTokenError as exc:
        raise TokenFirebaseInvalido("El token ha expirado. Renueva tu sesión.") from exc
    except (ValueError, fb_auth.InvalidIdTokenError, FirebaseError) as exc:
        raise TokenFirebaseInvalido("Token de Firebase inválido o expirado.") from exc


def validar_token(token: str) -> bool:
    try:
        verificar_token(token)
        return True
    except TokenFirebaseInvalido:
        return False


def obtener_uid(token: str) -> str:
    return verificar_token(token)["uid"]


def _firestore():
    return fb_firestore.client(app=_firebase_app())


def _doc_actividad(actividad_id):
    return _firestore().collection("actividades").document(str(actividad_id))


def coleccion_actividad_chat(actividad_id):
    return _doc_actividad(actividad_id).collection("mensajes")


def sincronizar_sala_chat_actividad(actividad: Actividad) -> None:
    try:
        _doc_actividad(actividad.pk).set(
            {
                "actividad_id": str(actividad.pk),
                "titulo": actividad.titulo,
                "creador_usuario_id": str(actividad.creador.usuario_id),
                "estado": actividad.estado,
                "actualizado_en": fb_firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
    except Exception:
        logger.exception("No se pudo sincronizar sala de chat en Firestore (%s)", actividad.pk)


def agregar_miembro_chat(actividad_id, firebase_uid: str) -> None:
    _doc_actividad(actividad_id).collection("miembros").document(firebase_uid).set(
        {"activo": True, "desde": fb_firestore.SERVER_TIMESTAMP}
    )


def quitar_miembro_chat(actividad_id, firebase_uid: str) -> None:
    _doc_actividad(actividad_id).collection("miembros").document(firebase_uid).delete()


def moderar_chat(actividad_id, mensaje_id, admin_id) -> bool:
    """Oculta (no borra) un mensaje para conservar evidencia."""
    ref = coleccion_actividad_chat(actividad_id).document(str(mensaje_id))
    if not ref.get().exists:
        return False
    ref.update(
        {
            "oculto": True,
            "moderado_por": str(admin_id),
            "moderado_en": fb_firestore.SERVER_TIMESTAMP,
        }
    )
    return True


def crear_notificacion_usuario(
    firebase_uid: str,
    titulo: str,
    mensaje: str,
    tipo: str = "general",
    metadata: dict | None = None,
) -> None:
    if not firebase_uid:
        return
    try:
        _firestore().collection("usuarios_notificaciones").document(firebase_uid).collection(
            "items"
        ).add(
            {
                "titulo": titulo,
                "mensaje": mensaje,
                "tipo": tipo,
                "leida": False,
                "metadata": metadata or {},
                "creado_en": fb_firestore.SERVER_TIMESTAMP,
            }
        )
    except Exception:
        logger.exception("No se pudo crear notificación en Firestore para uid %s", firebase_uid)


# CLOUDINARY
def _configurar_cloudinary() -> None:
    cloud_name = getattr(settings, "CLOUDINARY_CLOUD_NAME", "")
    api_key = getattr(settings, "CLOUDINARY_API_KEY", "")
    api_secret = getattr(settings, "CLOUDINARY_API_SECRET", "")
    if cloud_name and api_key and api_secret:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )


def _validar_archivo(
    archivo,
    tipos_mime: set[str],
    extensiones: set[str],
    tamano_max: int,
) -> str:
    nombre = getattr(archivo, "name", "") or ""
    extension = os.path.splitext(nombre)[1].lower()
    if extension not in extensiones:
        raise ArchivoInvalido("Extensión de archivo no permitida.")

    content_type = (getattr(archivo, "content_type", None) or "").lower()
    if content_type not in tipos_mime:
        raise ArchivoInvalido("Tipo de archivo no permitido.")

    if extension == ".pdf" and content_type != "application/pdf":
        raise ArchivoInvalido("El contenido no coincide con un archivo PDF válido.")
    if extension != ".pdf" and not content_type.startswith("image/"):
        raise ArchivoInvalido("El contenido no coincide con una imagen válida.")

    tamano = getattr(archivo, "size", 0) or 0
    if tamano <= 0 or tamano > tamano_max:
        raise ArchivoInvalido("El tamaño del archivo no es válido o supera el máximo permitido.")

    return extension


def subir_imagen(archivo, carpeta: str = "actividades") -> Imagen:
    """Sube una imagen pública y devuelve el embebido Imagen (solo public_id)."""
    _validar_archivo(archivo, _TIPOS_IMAGEN, _EXTENSIONES_IMAGEN, _TAMANO_MAX_IMAGEN)
    _configurar_cloudinary()
    resultado = cloudinary.uploader.upload(
        archivo,
        folder=carpeta,
        resource_type="image",
        type="upload",
        allowed_formats=["jpg", "jpeg", "png", "webp"],
    )
    return Imagen(public_id=resultado["public_id"])


def subir_documento(archivo, carpeta: str = "verificaciones") -> DocumentoPrivado:
    """Sube un documento sensible como type='authenticated' con formatos estrictos."""
    extension = _validar_archivo(
        archivo, _TIPOS_DOCUMENTO, _EXTENSIONES_DOCUMENTO, _TAMANO_MAX_DOCUMENTO
    )
    _configurar_cloudinary()
    es_pdf = extension == ".pdf"
    recurso_cloudinary = "raw" if es_pdf else "image"

    resultado = cloudinary.uploader.upload(
        archivo,
        folder=carpeta,
        resource_type=recurso_cloudinary,
        type="authenticated",
        allowed_formats=_FORMATOS_CLOUDINARY_DOC,
    )
    formato = (resultado.get("format") or extension.lstrip(".")).lower()
    return DocumentoPrivado(
        public_id=resultado["public_id"],
        resource_type=(
            DocumentoPrivado.TipoRecurso.ARCHIVO
            if es_pdf
            else DocumentoPrivado.TipoRecurso.IMAGEN
        ),
        formato=formato,
    )


def generar_url_firmada(documento: DocumentoPrivado, segundos: int = 300) -> str:
    """URL de descarga con vencimiento para un DocumentoPrivado. Solo para admins."""
    _configurar_cloudinary()
    return cloudinary.utils.private_download_url(
        documento.public_id,
        documento.formato,
        resource_type=documento.resource_type,
        type="authenticated",
        expires_at=int(time.time()) + segundos,
    )


# MONGODB: ÍNDICES NATIVOS E INSCRIPCIONES ATÓMICAS
@lru_cache(maxsize=1)
def _obtener_db_nativa():
    """Conexión cruda y directa a PyMongo, saltando todos los wrappers de Django."""
    db_settings = settings.DATABASES["default"]
    # Nos conectamos explícitamente a la URI y seleccionamos el nombre de la BD
    cliente = MongoClient(db_settings["HOST"])
    return cliente[db_settings["NAME"]]


def _coleccion_actividades():
    return _obtener_db_nativa()[Actividad._meta.db_table]


def _coleccion_inscripciones():
    return _obtener_db_nativa()[Inscripcion._meta.db_table]


def _coleccion_usuarios():
    return _obtener_db_nativa()[Usuario._meta.db_table]


def crear_indices_nativos() -> None:
    """Crea índices complejos en MongoDB que el ORM aún no soporta nativamente."""
    _coleccion_actividades().create_index(
        [("ubicacion.geo_exacta", "2dsphere")],
        name="idx_act_geo_2dsphere",
    )
    
    _coleccion_usuarios().create_index(
        [("verificacion_publicador.rut", 1)],
        name="uniq_usuario_rut",
        unique=True,
        partialFilterExpression={"verificacion_publicador.rut": {"$type": "string"}},
    )

    _coleccion_usuarios().create_index(
        [("telefono", 1)],
        name="uniq_usuario_telefono",
        unique=True,
        partialFilterExpression={"telefono": {"$gt": ""}},
    )


def _descontar_cupo_atomico(actividad_id) -> bool:
    resultado = _coleccion_actividades().find_one_and_update(
        filter={
            "_id": ObjectId(str(actividad_id)),
            "estado": Actividad.Estado.PUBLICADA.value,
            "cupos.disponible": {"$gt": 0},
        },
        update={
            "$inc": {"cupos.disponible": -1},
            "$set": {"auditoria.actualizado_el": timezone.now()},
        },
        return_document=True,
    )
    return resultado is not None


def _devolver_cupo_atomico(actividad_id) -> None:
    _coleccion_actividades().find_one_and_update(
        filter={
            "_id": ObjectId(str(actividad_id)),
            "$expr": {"$lt": ["$cupos.disponible", "$cupos.total"]},
        },
        update={
            "$inc": {"cupos.disponible": 1},
            "$set": {"auditoria.actualizado_el": timezone.now()},
        },
    )


def _marcar_inscripcion_cancelada_atomica(inscripcion_id, fecha_cancelacion) -> bool:
    """Transiciona de forma atómica una inscripción confirmada a cancelada una sola vez."""
    resultado = _coleccion_inscripciones().update_one(
        filter={
            "_id": ObjectId(str(inscripcion_id)),
            "estado": Inscripcion.Estado.CONFIRMADA.value,
        },
        update={
            "$set": {
                "estado": Inscripcion.Estado.CANCELADA.value,
                "fecha_cancelacion": fecha_cancelacion,
            }
        },
    )
    return resultado.modified_count == 1


def _es_conflicto_transitorio(exc) -> bool:
    for _ in range(5):
        if exc is None:
            return False
        if isinstance(exc, PyMongoError) and exc.has_error_label("TransientTransactionError"):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _sincronizar_chat_seguro(accion, actividad_pk, firebase_uid: str) -> None:
    try:
        accion(actividad_pk, firebase_uid)
    except Exception:
        logger.exception(
            "No se pudo sincronizar membresía de chat (actividad=%s, uid=%s)",
            actividad_pk,
            firebase_uid,
        )


def inscribir(usuario, actividad_id, ip_origen=None, dispositivo: str = "") -> Inscripcion:
    """Inscribe o reactiva inscripción con control atómico de cupos."""
    for intento in range(_MAX_REINTENTOS):
        try:
            try:
                actividad = Actividad.objects.get(pk=actividad_id)
            except Actividad.DoesNotExist as exc:
                raise ActividadNoDisponible("La actividad no existe.") from exc

            ahora = timezone.now()
            if actividad.estado != Actividad.Estado.PUBLICADA or actividad.horario.inicio <= ahora:
                raise ActividadNoDisponible("La actividad no admite inscripciones.")
            if actividad.creador.usuario_id == usuario.pk:
                raise ActividadNoDisponible("No puedes inscribirte en tu propia actividad.")

            inscripcion_existente = Inscripcion.objects.filter(
                actividad=actividad, usuario=usuario
            ).first()
            if inscripcion_existente and inscripcion_existente.estado == Inscripcion.Estado.CONFIRMADA:
                raise YaInscrito("Ya estás inscrito en esta actividad.")

            if not _descontar_cupo_atomico(actividad.pk):
                raise SinCupos("No quedan cupos disponibles.")

            try:
                resumen = ActividadResumen(
                    titulo=actividad.titulo,
                    fecha_inicio=actividad.horario.inicio,
                    comuna=actividad.ubicacion.comuna if actividad.ubicacion else "",
                    imagen_portada_public_id=(
                        actividad.imagen_portada.public_id if actividad.imagen_portada else ""
                    ),
                )
                participante = ParticipanteResumen(
                    nombre_mostrar=usuario.nombre_mostrar,
                    correo=usuario.correo,
                    telefono=usuario.telefono or "",
                )
                auditoria = AuditoriaInscripcion(
                    ip_origen=ip_origen, dispositivo=dispositivo[:255]
                )

                with transaction.atomic():
                    if inscripcion_existente:
                        inscripcion_existente.estado = Inscripcion.Estado.CONFIRMADA
                        inscripcion_existente.fecha_inscripcion = ahora
                        inscripcion_existente.fecha_cancelacion = None
                        inscripcion_existente.actividad_resumen = resumen
                        inscripcion_existente.participante_resumen = participante
                        inscripcion_existente.auditoria = auditoria
                        inscripcion_existente.save()
                        inscripcion = inscripcion_existente
                    else:
                        inscripcion = Inscripcion.objects.create(
                            actividad=actividad,
                            usuario=usuario,
                            actividad_resumen=resumen,
                            participante_resumen=participante,
                            auditoria=auditoria,
                        )
            except Exception:
                _devolver_cupo_atomico(actividad.pk)
                raise

            break
        except ErrorServicio:
            raise
        except Exception as exc:
            if _es_conflicto_transitorio(exc) and intento < _MAX_REINTENTOS - 1:
                continue
            raise

    actividad_pk_canonico = actividad.pk
    _sincronizar_chat_seguro(agregar_miembro_chat, actividad_pk_canonico, usuario.firebase_uid)
    crear_notificacion_usuario(
        firebase_uid=usuario.firebase_uid,
        titulo="Inscripción confirmada",
        mensaje=f"Tu cupo en '{actividad.titulo}' quedó confirmado.",
        tipo="inscripcion_confirmada",
        metadata={
            "actividad_id": str(actividad_pk_canonico),
            "inscripcion_id": str(inscripcion.pk),
        },
    )
    return inscripcion


def cancelar_inscripcion(usuario, actividad_id) -> Inscripcion:
    """Cancela una inscripción confirmada y devuelve el cupo de forma atómica."""
    for intento in range(_MAX_REINTENTOS):
        try:
            inscripcion = Inscripcion.objects.filter(
                actividad_id=actividad_id,
                usuario=usuario,
                estado=Inscripcion.Estado.CONFIRMADA,
            ).first()
            if not inscripcion:
                raise InscripcionNoEncontrada("No tienes una inscripción activa.")

            try:
                actividad = Actividad.objects.get(pk=inscripcion.actividad_id)
            except Actividad.DoesNotExist as exc:
                raise ActividadNoDisponible("La actividad no existe.") from exc

            if actividad.horario.inicio <= timezone.now():
                raise ActividadNoDisponible("La actividad ya comenzó.")

            ahora = timezone.now()
            if not _marcar_inscripcion_cancelada_atomica(inscripcion.pk, ahora):
                raise InscripcionNoEncontrada("No tienes una inscripción activa.")

            _devolver_cupo_atomico(actividad.pk)
            inscripcion.refresh_from_db()
            break
        except ErrorServicio:
            raise
        except Exception as exc:
            if _es_conflicto_transitorio(exc) and intento < _MAX_REINTENTOS - 1:
                continue
            raise

    actividad_pk_canonico = actividad.pk
    _sincronizar_chat_seguro(quitar_miembro_chat, actividad_pk_canonico, usuario.firebase_uid)
    crear_notificacion_usuario(
        firebase_uid=usuario.firebase_uid,
        titulo="Inscripción cancelada",
        mensaje=f"Cancelaste tu inscripción en '{inscripcion.actividad_resumen.titulo}'.",
        tipo="inscripcion_cancelada",
        metadata={
            "actividad_id": str(actividad_pk_canonico),
            "inscripcion_id": str(inscripcion.pk),
        },
    )
    return inscripcion