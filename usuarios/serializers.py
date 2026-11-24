from bson import ObjectId
from rest_framework import serializers
from .models import DatosPersona, DatosEntidad, Imagen, Taxonomia, TaxonomiaRef, Usuario

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