
from dataclasses import dataclass
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from .models import Usuario
from .services import TokenFirebaseInvalido, verificar_token


@dataclass
class IdentidadFirebase:
    """Identidad verificada en Firebase antes de crear el perfil en MongoDB."""

    firebase_uid: str
    correo: str = ""
    email_verified: bool = False

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def es_admin(self) -> bool:
        return False

    @property
    def es_publicador(self) -> bool:
        return False


class FirebaseAuthentication(BaseAuthentication):
    keyword = "Bearer"
    requiere_perfil = True

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes:
            return None
        if len(partes) != 2 or partes[0].lower() != b"bearer":
            raise AuthenticationFailed(
                "Formato de encabezado inválido. Use: Authorization: Bearer <token>."
            )

        token = partes[1].decode("utf-8").strip()
        if not token:
            raise AuthenticationFailed("Token de autenticación vacío.")

        try:
            decodificado = verificar_token(token)
        except TokenFirebaseInvalido as exc:
            raise AuthenticationFailed(str(exc)) from exc
        except Exception as exc:
            raise AuthenticationFailed(
                "No fue posible verificar el token de autenticación."
            ) from exc

        uid = decodificado.get("uid") or decodificado.get("sub")
        if not uid:
            raise AuthenticationFailed("El token no contiene un UID válido.")

        correo = (decodificado.get("email") or "").strip().lower()
        email_verified = bool(decodificado.get("email_verified", False))

        if not self.requiere_perfil:
            return (
                IdentidadFirebase(
                    firebase_uid=uid,
                    correo=correo,
                    email_verified=email_verified,
                ),
                decodificado,
            )

        usuario = Usuario.objects.filter(firebase_uid=uid).first()
        if usuario is None:
            raise AuthenticationFailed(
                "Perfil no registrado. Completa el registro antes de continuar."
            )
        if not usuario.is_active:
            raise AuthenticationFailed("Esta cuenta se encuentra desactivada o suspendida.")

        return (usuario, decodificado)

    def authenticate_header(self, request):
        return self.keyword


class FirebaseTokenSinPerfil(FirebaseAuthentication):
    requiere_perfil = False