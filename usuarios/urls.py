from django.urls import path
from usuarios.views import (
    ActividadDetalleView,
    ActividadFotoView,
    ActividadInscripcionView,
    ActividadListCreateView,
    CerrarSesionView,
    DocumentosEntidadView,
    HabilidadesPerfilView,
    PerfilDetalleView,
    PerfilFotoView,
    RegistroUsuarioView,
)

# ===========================================================================
# RUTAS OMITIDAS EN EL BACKEND (Delegadas al Frontend con Firebase):
# - path('auth/login/')            -> Manejado por Firebase SDK
# - path('auth/logout/')           -> Manejado por Firebase SDK
# - path('auth/recuperar-clave/')  -> Manejado por Firebase SDK
# ===========================================================================


urlpatterns = [
    path("auth/registro/", RegistroUsuarioView.as_view(), name="auth-registro"),
    path("auth/cerrar/", CerrarSesionView.as_view(), name="auth-cerrar"),
    path("perfil/", PerfilDetalleView.as_view(), name="perfil-detalle"),
    path("perfil/foto/", PerfilFotoView.as_view(), name="perfil-foto"),
    path("perfil/habilidades/", HabilidadesPerfilView.as_view(), name="perfil-habilidades"),
    path("actividades/", ActividadListCreateView.as_view(), name="actividades-list-create"),
    path("actividades/<str:actividad_id>/", ActividadDetalleView.as_view(), name="actividades-detalle"),
    path("actividades/<str:actividad_id>/portada/", ActividadFotoView.as_view(), name="actividades-portada"),
    path("actividades/<str:actividad_id>/inscribir/", ActividadInscripcionView.as_view(), name="actividades-inscribir"),
    path("perfil/documentos/", DocumentosEntidadView.as_view(), name="perfil-documentos"),
]