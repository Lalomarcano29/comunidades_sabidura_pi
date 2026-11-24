from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from firebase_admin import auth as fb_auth
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import FirebaseTokenSinPerfil
from .models import DatosEntidad, DatosPersona, Usuario
from .serializers import (
    HabilidadesUpdateSerializer,
    PerfilConsultaSerializer,
    PerfilUpdateSerializer,
    RegistroUsuarioSerializer,
)
from .services import ArchivoInvalido, subir_imagen

RESPUESTAS_HTTP_COMUNES = {
    401: OpenApiResponse(description="401 Unauthorized: Falta el token de autenticación o es inválido/expirado."),
    403: OpenApiResponse(description="403 Forbidden: Autenticado, pero sin permisos o tipo de cuenta/rol no autorizado."),
    405: OpenApiResponse(description="405 Method Not Allowed: Método HTTP no permitido en este endpoint."),
    429: OpenApiResponse(description="429 Too Many Requests: Límite de peticiones excedido."),
    500: OpenApiResponse(description="500 Internal Server Error: Error interno no controlado en el servidor."),
}


def respuestas_http(especificas=None):
    """Combina las respuestas HTTP estándar con las específicas de cada operación."""
    if not especificas:
        return dict(RESPUESTAS_HTTP_COMUNES)
    return {**RESPUESTAS_HTTP_COMUNES, **especificas}


def guardar_usuario_o_responder(usuario: Usuario, status_code: int = status.HTTP_200_OK) -> Response:
    """Guarda el usuario manejando errores de validación del modelo y devuelve la respuesta serializada."""
    try:
        usuario.save()
    except DjangoValidationError as exc:
        detalle = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        return Response(detalle, status=status.HTTP_400_BAD_REQUEST)

    return Response(PerfilConsultaSerializer(usuario).data, status=status_code)


def construir_submodelos_registro(data: dict) -> tuple[DatosPersona | None, DatosEntidad | None]:
    """Instancia DatosPersona o DatosEntidad según el tipo de cuenta."""
    tipo = data["tipo_cuenta"]

    if tipo == Usuario.TipoCuenta.PERSONA and data.get("datos_persona"):
        dp = data["datos_persona"]
        return (
            DatosPersona(
                nombres=dp["nombres"],
                apellidos=dp["apellidos"],
                fecha_nacimiento=dp["fecha_nacimiento"],
                habilidades=dp.get("habilidades", []),
            ),
            None,
        )

    if tipo in (Usuario.TipoCuenta.EMPRESA, Usuario.TipoCuenta.INSTITUCION) and data.get("datos_entidad"):
        de = data["datos_entidad"]
        return (
            None,
            DatosEntidad(
                razon_social=de["razon_social"],
                fecha_creacion=de["fecha_creacion"],
            ),
        )

    return None, None


def aplicar_cambios_perfil(usuario: Usuario, data: dict) -> None:
    """Aplica actualizaciones parciales sobre Usuario y sus subdocumentos."""
    for campo in ("nombre_mostrar", "biografia", "telefono"):
        if campo in data:
            setattr(usuario, campo, data[campo])

    if usuario.datos_persona:
        for campo in ("nombres", "apellidos", "fecha_nacimiento"):
            if campo in data:
                setattr(usuario.datos_persona, campo, data[campo])

    if usuario.datos_entidad and "razon_social" in data:
        usuario.datos_entidad.razon_social = data["razon_social"]


class RegistroUsuarioView(APIView):
    authentication_classes = [FirebaseTokenSinPerfil]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Registrar nuevo perfil",
        description="Crea un perfil de Persona, Empresa o Institución asociado al token de Firebase.",
        request=RegistroUsuarioSerializer,
        responses=respuestas_http({
            201: PerfilConsultaSerializer,
            400: OpenApiResponse(description="400 Bad Request: JSON mal formado o campos obligatorios faltantes."),
            409: OpenApiResponse(description="409 Conflict: Ya existe un perfil registrado para este usuario."),
            422: OpenApiResponse(description="422 Unprocessable Content: Falla en validación de datos de persona/entidad o correo."),
        }),
    )
    def post(self, request):
        identidad = request.user
        if not getattr(identidad, "firebase_uid", None):
            return Response({"detail": "Identidad de Firebase no disponible."}, status=status.HTTP_401_UNAUTHORIZED)

        if Usuario.objects.filter(firebase_uid=identidad.firebase_uid).exists():
            return Response({"detail": "Ya existe un perfil registrado para este usuario."}, status=status.HTTP_409_CONFLICT)

        serializer = RegistroUsuarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        correo = (getattr(identidad, "correo", "") or request.data.get("correo") or "").strip().lower()
        if not correo:
            return Response({"correo": ["No se pudo obtener un correo válido desde el token."]}, status=status.HTTP_400_BAD_REQUEST)

        datos_persona, datos_entidad = construir_submodelos_registro(data)
        usuario = Usuario(
            firebase_uid=identidad.firebase_uid,
            correo=correo,
            tipo_cuenta=data["tipo_cuenta"],
            nombre_mostrar=data["nombre_mostrar"],
            biografia=data.get("biografia", ""),
            telefono=data.get("telefono", ""),
            datos_persona=datos_persona,
            datos_entidad=datos_entidad,
        )
        return guardar_usuario_o_responder(usuario, status_code=status.HTTP_201_CREATED)


class CerrarSesionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cerrar sesión",
        description="Revoca los refresh tokens de Firebase en el servidor. El frontend también debe ejecutar auth.signOut().",
        request=None,
        responses=respuestas_http({
            200: OpenApiResponse(description="200 OK: Sesión cerrada correctamente y tokens revocados."),
        }),
    )
    def post(self, request):
        try:
            fb_auth.revoke_refresh_tokens(request.user.firebase_uid)
        except Exception:
            pass
        return Response({"detail": "Sesión cerrada correctamente y tokens revocados."}, status=status.HTTP_200_OK)


class PerfilDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Consultar perfil personal",
        description="Obtiene los datos del perfil del usuario autenticado.",
        responses=respuestas_http({
            200: PerfilConsultaSerializer,
            404: OpenApiResponse(description="404 Not Found: Perfil asociado no encontrado."),
        }),
    )
    def get(self, request):
        return Response(PerfilConsultaSerializer(request.user).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Editar datos personales",
        description="Actualiza parcialmente los datos del perfil de Persona o Entidad.",
        request=PerfilUpdateSerializer,
        responses=respuestas_http({
            200: PerfilConsultaSerializer,
            400: OpenApiResponse(description="400 Bad Request: JSON mal formado o datos inválidos."),
            422: OpenApiResponse(description="422 Unprocessable Content: Datos con formato válido pero inválidos para el modelo."),
        }),
    )
    def patch(self, request):
        usuario = request.user
        serializer = PerfilUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        aplicar_cambios_perfil(usuario, serializer.validated_data)
        return guardar_usuario_o_responder(usuario)


class PerfilFotoView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Actualizar fotografía de perfil",
        description="Sube una imagen en multipart/form-data ('foto' o 'imagen') a Cloudinary y actualiza el perfil.",
        request=inline_serializer(
            name="FotoUploadRequest",
            fields={"foto": serializers.ImageField(required=True, help_text="Archivo de imagen (jpg, png, webp)")},
        ),
        responses=respuestas_http({
            200: PerfilConsultaSerializer,
            400: OpenApiResponse(description="400 Bad Request: Archivo faltante o rechazado por validación."),
            415: OpenApiResponse(description="415 Unsupported Media Type: Se requiere multipart/form-data o archivo de imagen válido."),
            422: OpenApiResponse(description="422 Unprocessable Content: Imagen inválida o corrupta."),
            502: OpenApiResponse(description="502 Bad Gateway: Error al comunicarse con el servicio de almacenamiento (Cloudinary)."),
        }),
    )
    def post(self, request):
        archivo = request.FILES.get("foto") or request.FILES.get("imagen")
        if not archivo:
            return Response({"foto": ["Debes adjuntar un archivo en el campo 'foto'."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            imagen_embebida = subir_imagen(archivo, carpeta="perfiles")
        except ArchivoInvalido as exc:
            return Response({"foto": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        request.user.foto_perfil = imagen_embebida
        return guardar_usuario_o_responder(request.user)


class HabilidadesPerfilView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Consultar habilidades destacadas",
        description="Obtiene las habilidades destacadas del perfil tipo persona autenticado.",
        responses=respuestas_http({
            200: inline_serializer(
                name="HabilidadesDestacadasResponse",
                fields={"habilidades_destacadas": serializers.ListField(child=serializers.DictField())},
            ),
        }),
    )
    def get(self, request):
        serializer = PerfilConsultaSerializer(request.user)
        return Response({"habilidades_destacadas": serializer.data["habilidades_destacadas"]}, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar habilidades (Reemplazo total)",
        description="Reemplaza la lista completa de habilidades destacadas de un perfil tipo persona.",
        request=HabilidadesUpdateSerializer,
        responses=respuestas_http({
            200: PerfilConsultaSerializer,
            400: OpenApiResponse(description="400 Bad Request: Perfil no es de persona o taxonomía inválida."),
            422: OpenApiResponse(description="422 Unprocessable Content: Regla de negocio no cumplida en habilidades."),
        }),
    )
    def put(self, request):
        return self._actualizar(request)

    @extend_schema(
        summary="Actualizar habilidades (Parcial)",
        description="Actualiza la lista de habilidades destacadas de un perfil tipo persona.",
        request=HabilidadesUpdateSerializer,
        responses=respuestas_http({
            200: PerfilConsultaSerializer,
            400: OpenApiResponse(description="400 Bad Request: Perfil no es de persona o taxonomía inválida."),
            422: OpenApiResponse(description="422 Unprocessable Content: Regla de negocio no cumplida en habilidades."),
        }),
    )
    def patch(self, request):
        return self._actualizar(request)

    def _actualizar(self, request):
        usuario = request.user
        if not usuario.datos_persona:
            return Response({"detail": "El apartado de habilidades aplica a perfiles de persona."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = HabilidadesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usuario.datos_persona.habilidades = serializer.validated_data["habilidades"]
        return guardar_usuario_o_responder(usuario)