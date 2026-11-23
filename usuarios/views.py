from django.core.exceptions import ValidationError as DjangoValidationError
from firebase_admin import auth as fb_auth
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .authentication import FirebaseTokenSinPerfil
from .models import DatosPersona, DatosEntidad, Usuario
from .serializers import (
    HabilidadesUpdateSerializer,
    PerfilConsultaSerializer,
    PerfilUpdateSerializer,
    RegistroUsuarioSerializer,
)
from .services import ArchivoInvalido, subir_imagen

#------------------------------------------------------------------------------------------------------
from .docs import registro_usuario_schema

@registro_usuario_schema
class RegistroUsuarioView(APIView):
    authentication_classes = [FirebaseTokenSinPerfil]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        identidad = request.user
        if not getattr(identidad, "firebase_uid", None):
            return Response({"detail": "Identidad de Firebase no disponible."}, status=status.HTTP_401_UNAUTHORIZED)
#------------------------------------------------------------------------------------------------------

class RegistroUsuarioView(APIView):
    authentication_classes = [FirebaseTokenSinPerfil]
    permission_classes = [IsAuthenticated]

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

        datos_persona = None
        datos_entidad = None
        
        if data["tipo_cuenta"] == Usuario.TipoCuenta.PERSONA and data.get("datos_persona"):
            dp = data["datos_persona"]
            datos_persona = DatosPersona(
                nombres=dp["nombres"],
                apellidos=dp["apellidos"],
                fecha_nacimiento=dp["fecha_nacimiento"],
                habilidades=dp.get("habilidades", []),
            )
        elif data["tipo_cuenta"] in (Usuario.TipoCuenta.EMPRESA, Usuario.TipoCuenta.INSTITUCION) and data.get("datos_entidad"):
            de = data["datos_entidad"]
            datos_entidad = DatosEntidad(
                razon_social=de["razon_social"],
                fecha_creacion=de["fecha_creacion"]
            )

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

        try:
            usuario.save()
        except DjangoValidationError as exc:
            return Response(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PerfilConsultaSerializer(usuario).data, status=status.HTTP_201_CREATED)


class CerrarSesionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            fb_auth.revoke_refresh_tokens(request.user.firebase_uid)
        except Exception:
            pass
        return Response({"detail": "Sesión cerrada correctamente y tokens revocados."}, status=status.HTTP_200_OK)


class PerfilDetalleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PerfilConsultaSerializer(request.user).data, status=status.HTTP_200_OK)

    def patch(self, request):
        usuario = request.user
        serializer = PerfilUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        for campo in ("nombre_mostrar", "biografia", "telefono"):
            if campo in data:
                setattr(usuario, campo, data[campo])

        if usuario.datos_persona and any(k in data for k in ("nombres", "apellidos", "fecha_nacimiento")):
            if "nombres" in data:
                usuario.datos_persona.nombres = data["nombres"]
            if "apellidos" in data:
                usuario.datos_persona.apellidos = data["apellidos"]
            if "fecha_nacimiento" in data:
                usuario.datos_persona.fecha_nacimiento = data["fecha_nacimiento"]
                
        if usuario.datos_entidad and "razon_social" in data:
            usuario.datos_entidad.razon_social = data["razon_social"]

        try:
            usuario.save()
        except DjangoValidationError as exc:
            return Response(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PerfilConsultaSerializer(usuario).data, status=status.HTTP_200_OK)


class PerfilFotoView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        archivo = request.FILES.get("foto") or request.FILES.get("imagen")
        if not archivo:
            return Response({"foto": ["Debes adjuntar un archivo en el campo 'foto'."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            imagen_embebida = subir_imagen(archivo, carpeta="perfiles")
        except ArchivoInvalido as exc:
            return Response({"foto": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        usuario = request.user
        usuario.foto_perfil = imagen_embebida
        try:
            usuario.save()
        except DjangoValidationError as exc:
            return Response(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PerfilConsultaSerializer(usuario).data, status=status.HTTP_200_OK)


class HabilidadesPerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = PerfilConsultaSerializer(request.user)
        return Response({"habilidades_destacadas": serializer.data["habilidades_destacadas"]}, status=status.HTTP_200_OK)

    def put(self, request):
        return self._actualizar(request)

    def patch(self, request):
        return self._actualizar(request)

    def _actualizar(self, request):
        usuario = request.user
        if not usuario.datos_persona:
            return Response({"detail": "El apartado de habilidades aplica a perfiles de persona."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = HabilidadesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usuario.datos_persona.habilidades = serializer.validated_data["habilidades"]
        try:
            usuario.save()
        except DjangoValidationError as exc:
            return Response(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PerfilConsultaSerializer(usuario).data, status=status.HTTP_200_OK)