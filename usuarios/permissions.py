from rest_framework.permissions import BasePermission
from .models import Usuario

class PuedePublicarActividad(BasePermission):
    message = "Debes ser una persona o una organización autorizada (publicador) para crear actividades."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        
        # Las personas naturales (el modelo ya validó que son mayores de 18 al registrarse)
        if user.tipo_cuenta == Usuario.TipoCuenta.PERSONA:
            return True
            
        # Las organizaciones deben tener el rol de PUBLICADOR (o ADMIN)
        if user.tipo_cuenta in (Usuario.TipoCuenta.EMPRESA, Usuario.TipoCuenta.INSTITUCION):
            return user.es_publicador
            
        return False