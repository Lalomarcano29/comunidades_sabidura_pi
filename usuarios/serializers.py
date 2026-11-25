from bson import ObjectId
from rest_framework import serializers
from .models import (
    Taxonomia,
    TaxonomiaRef,
    Usuario,
    Actividad,
)

class ImagenSerializer(serializers.Serializer):
    public_id = serializers.CharField(read_only=True)
    url = serializers.CharField(read_only=True)
    subido_en = serializers.DateTimeField(read_only=True)

class TaxonomiaRefSerializer(serializers.Serializer):
    taxonomia_id = serializers.CharField()
    nombre = serializers.CharField(max_length=100, required=False)

    def validate_taxonomia_id(self, value):
        if not ObjectId.is_valid(value):
            raise serializers.ValidationError("taxonomia_id debe ser un ObjectId válido.")
        return ObjectId(value)

class DatosPersonaSerializer(serializers.Serializer):
    nombres = serializers.CharField(max_length=100)
    apellidos = serializers.CharField(max_length=100)
    fecha_nacimiento = serializers.DateField()
    habilidades = TaxonomiaRefSerializer(many=True, required=False, default=list)

class DatosEntidadSerializer(serializers.Serializer):
    razon_social = serializers.CharField(max_length=200)
    fecha_creacion = serializers.DateField()

class RegistroUsuarioSerializer(serializers.Serializer):
    tipo_cuenta = serializers.ChoiceField(choices=Usuario.TipoCuenta.choices)
    nombre_mostrar = serializers.CharField(max_length=100)
    biografia = serializers.CharField(required=False, allow_blank=True, default="")
    telefono = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    datos_persona = DatosPersonaSerializer(required=False, allow_null=True)
    datos_entidad = DatosEntidadSerializer(required=False, allow_null=True)

    def validate(self, attrs):
        tipo_cuenta = attrs.get("tipo_cuenta")
        if tipo_cuenta == Usuario.TipoCuenta.PERSONA and not attrs.get("datos_persona"):
            raise serializers.ValidationError({"datos_persona": "Requerido para cuentas de tipo persona."})
        if tipo_cuenta in (Usuario.TipoCuenta.EMPRESA, Usuario.TipoCuenta.INSTITUCION) and not attrs.get("datos_entidad"):
            raise serializers.ValidationError({"datos_entidad": "Requerido para organizaciones."})
        return attrs

class PerfilConsultaSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True, source="pk")
    foto_perfil = ImagenSerializer(read_only=True)
    datos_persona = DatosPersonaSerializer(read_only=True) # <-- NUEVO
    datos_entidad = DatosEntidadSerializer(read_only=True) # <-- NUEVO
    habilidades_destacadas = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "correo",
            "tipo_cuenta",
            "rol",
            "nombre_mostrar",
            "foto_perfil",
            "biografia",
            "telefono",
            "datos_persona",
            "datos_entidad",
            "habilidades_destacadas",
            "fecha_registro",
        ]
        read_only_fields = fields

    def get_habilidades_destacadas(self, obj):
        if not obj.datos_persona or not obj.datos_persona.habilidades:
            return []
        return [
            {
                "taxonomia_id": str(item.taxonomia_id),
                "nombre": item.nombre,
            }
            for item in obj.datos_persona.habilidades
        ]

class PerfilUpdateSerializer(serializers.Serializer):
    nombre_mostrar = serializers.CharField(max_length=100, required=False)
    biografia = serializers.CharField(required=False, allow_blank=True)
    telefono = serializers.CharField(max_length=20, required=False, allow_blank=True)
    
    # Para Persona
    nombres = serializers.CharField(max_length=100, required=False)
    apellidos = serializers.CharField(max_length=100, required=False)
    fecha_nacimiento = serializers.DateField(required=False)
    
    # Para Entidad
    razon_social = serializers.CharField(max_length=200, required=False)

class HabilidadesUpdateSerializer(serializers.Serializer):
    habilidades = TaxonomiaRefSerializer(many=True)

    def validate_habilidades(self, items):
        resueltas = []
        for item in items:
            tax_id = item["taxonomia_id"]
            taxonomia = Taxonomia.objects.filter(
                pk=tax_id,
                tipo=Taxonomia.Tipo.HABILIDAD,
                activa=True,
            ).first()
            nombre = item.get("nombre") or (taxonomia.nombre if taxonomia else "")
            if not nombre:
                raise serializers.ValidationError(
                    f"No se encontró la habilidad '{tax_id}' ni se indicó un nombre."
                )
            resueltas.append(TaxonomiaRef(taxonomia_id=tax_id, nombre=nombre))
        return resueltas

class ClasificacionSerializer(serializers.Serializer):
    categoria = TaxonomiaRefSerializer()
    nivel_esfuerzo = TaxonomiaRefSerializer()
    accesibilidad = TaxonomiaRefSerializer(many=True, required=False, default=list)

    def _validar_taxonomia(self, tax_data, tipo_esperado):
        tax_id = tax_data["taxonomia_id"]
        tax = Taxonomia.objects.filter(pk=tax_id, tipo=tipo_esperado, activa=True).first()
        if not tax:
            raise serializers.ValidationError(f"La taxonomía '{tax_id}' no existe o no es de tipo '{tipo_esperado}'.")
        # Forzamos el nombre real de la BD para asegurar consistencia
        tax_data["nombre"] = tax.nombre
        return tax_data

    def validate(self, attrs):
        if "categoria" in attrs:
            attrs["categoria"] = self._validar_taxonomia(attrs["categoria"], Taxonomia.Tipo.CATEGORIA)
        if "nivel_esfuerzo" in attrs:
            attrs["nivel_esfuerzo"] = self._validar_taxonomia(attrs["nivel_esfuerzo"], Taxonomia.Tipo.NIVEL_ESFUERZO)
        
        if "accesibilidad" in attrs:
            resueltas = []
            for item in attrs["accesibilidad"]:
                resueltas.append(self._validar_taxonomia(item, Taxonomia.Tipo.ACCESIBILIDAD))
            attrs["accesibilidad"] = resueltas
            
        return attrs

class HorarioSerializer(serializers.Serializer):
    inicio = serializers.DateTimeField()
    fin = serializers.DateTimeField()
    duracion_minutos = serializers.IntegerField(read_only=True)

class CuposSerializer(serializers.Serializer):
    total = serializers.IntegerField(min_value=1)
    disponible = serializers.IntegerField(read_only=True)
    sin_cupos = serializers.SerializerMethodField()

    def get_sin_cupos(self, obj) -> bool:
        disponible = getattr(obj, "disponible", None)
        if disponible is None and isinstance(obj, dict):
            disponible = obj.get("disponible")
        return (disponible or 0) <= 0

class CostoSerializer(serializers.Serializer):
    monto = serializers.IntegerField(min_value=0, default=0, help_text="0 significa gratuita")
    es_gratuito = serializers.SerializerMethodField()

    def get_es_gratuito(self, obj) -> bool:
        monto = getattr(obj, "monto", None)
        if monto is None and isinstance(obj, dict):
            monto = obj.get("monto", 0)
        return (monto or 0) == 0

class PuntoGeoJSONSerializer(serializers.Serializer):
    coordinates = serializers.ListField(
        child=serializers.FloatField(), min_length=2, max_length=2,
        help_text="[longitud, latitud]"
    )

class UbicacionSerializer(serializers.Serializer):
    comuna = serializers.CharField(max_length=100)
    direccion_privada = serializers.CharField(max_length=255)
    geo_exacta = PuntoGeoJSONSerializer()

class CreadorSerializer(serializers.Serializer):
    usuario_id = serializers.CharField(read_only=True)
    nombre_mostrar = serializers.CharField(read_only=True)
    tipo_cuenta = serializers.CharField(read_only=True)

class ActividadSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True, source="pk")
    titulo = serializers.CharField(max_length=150)
    descripcion = serializers.CharField()
    modalidad = serializers.ChoiceField(choices=Actividad.Modalidad.choices)
    imagen_portada = ImagenSerializer(read_only=True)
    clasificacion = ClasificacionSerializer()
    horario = HorarioSerializer()
    cupos = CuposSerializer()
    costo = CostoSerializer(required=False)
    ubicacion = UbicacionSerializer(required=False, allow_null=True)
    creador = CreadorSerializer(read_only=True)
    estado = serializers.ChoiceField(choices=Actividad.Estado.choices, read_only=True)

    def validate(self, attrs):
        horario = attrs.get('horario')
        if horario and horario['inicio'] and horario['fin']:
            if horario['fin'] <= horario['inicio']:
                raise serializers.ValidationError({"horario": "La fecha/hora de término debe ser posterior al inicio."})

        modalidad = attrs.get('modalidad')
        if modalidad in (Actividad.Modalidad.PRESENCIAL, Actividad.Modalidad.MIXTA):
            if not attrs.get('ubicacion'):
                raise serializers.ValidationError({"ubicacion": "La ubicación es obligatoria para actividades presenciales o mixtas."})
            
            coords = attrs['ubicacion']['geo_exacta']['coordinates']
            if not (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
                raise serializers.ValidationError({"ubicacion": "Coordenadas geográficas fuera de rango."})
                
        return attrs