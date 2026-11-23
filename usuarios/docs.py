from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from .serializers import RegistroUsuarioSerializer, PerfilConsultaSerializer

# Diccionario de documentación para RegistroUsuarioView
registro_usuario_schema = extend_schema_view(
    post=extend_schema(
        summary="Registrar nuevo perfil",
        description="Crea un perfil de Persona o Institución asociado al token de Firebase.",
        request=RegistroUsuarioSerializer,
        responses={
            201: PerfilConsultaSerializer,
            400: OpenApiResponse(description="Error de validación (faltan datos)."),
            409: OpenApiResponse(description="El usuario ya tiene un perfil registrado.")
        }
    )
)