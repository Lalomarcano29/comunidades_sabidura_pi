#Expresiones regulares, normalizadores y validadores de dominio (Chile).

import re
from datetime import date

from django.core.exceptions import ValidationError

REGEX_NOMBRE_PERSONA = re.compile(
    r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[ '-][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$"
)
REGEX_NOMBRE_MOSTRAR = re.compile(
    r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.,&()'-]+(?: [A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ.,&()'-]+)*$"
)
REGEX_TELEFONO_CL = re.compile(r"^\+56(?:9\d{8}|[2-7]\d{8})$")
REGEX_RUT = re.compile(r"^(\d{7,8})-([\dK])$")


def limpiar_espacios(valor):
    """Colapsa espacios múltiples internos y recorta extremos."""
    if not valor:
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip()


def validar_nombre_persona(valor):
    limpio = limpiar_espacios(valor)
    if len(limpio) < 2 or not REGEX_NOMBRE_PERSONA.fullmatch(limpio):
        raise ValidationError(
            "Solo se permiten letras, espacios simples, guiones o apóstrofes (mínimo 2 caracteres)."
        )


def validar_nombre_mostrar(valor):
    limpio = limpiar_espacios(valor)
    if len(limpio) < 2 or not REGEX_NOMBRE_MOSTRAR.fullmatch(limpio):
        raise ValidationError(
            "El nombre contiene caracteres no permitidos o espacios consecutivos."
        )


def normalizar_telefono_cl(valor):
    """Normaliza teléfonos chilenos a formato E.164 (+569XXXXXXXX o +562XXXXXXXX)."""
    if not valor:
        return ""
    limpio = re.sub(r"[\s().-]", "", str(valor))
    if limpio.startswith("0056"):
        limpio = "+56" + limpio[4:]
    elif limpio.startswith("56") and len(limpio) == 11:
        limpio = "+" + limpio
    elif re.fullmatch(r"9\d{8}", limpio) or re.fullmatch(r"[2-7]\d{8}", limpio):
        limpio = "+56" + limpio
    return limpio


def validar_telefono_cl(valor):
    normalizado = normalizar_telefono_cl(valor)
    if not normalizado:
        return
    if not REGEX_TELEFONO_CL.fullmatch(normalizado):
        raise ValidationError(
            "El teléfono debe corresponder a un número chileno válido (+569XXXXXXXX o +562XXXXXXXX)."
        )


def normalizar_rut(valor):
    """'12.345.678-k' o '12345678k' -> '12345678-K'."""
    if not valor:
        return None
    limpio = re.sub(r"[.\s]", "", str(valor)).upper()
    if "-" not in limpio and len(limpio) > 1:
        limpio = f"{limpio[:-1]}-{limpio[-1]}"
    return limpio


def validar_rut(rut):
    """Valida formato y dígito verificador (módulo 11)."""
    rut_limpio = normalizar_rut(rut)
    if not rut_limpio:
        return
    match = REGEX_RUT.fullmatch(rut_limpio)
    if not match:
        raise ValidationError("El RUT debe tener el formato 12345678-9.")
    cuerpo, dv = match.groups()
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    if dv != esperado:
        raise ValidationError("El dígito verificador del RUT no es válido.")


def calcular_edad(fecha_nacimiento):
    """Calcula edad exacta y valida que la fecha no sea futura."""
    if not fecha_nacimiento:
        return None
    hoy = date.today()
    if fecha_nacimiento > hoy:
        raise ValidationError("La fecha de nacimiento no puede ser futura.")
    return (
        hoy.year
        - fecha_nacimiento.year
        - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )