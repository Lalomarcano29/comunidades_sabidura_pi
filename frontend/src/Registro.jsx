import { useState } from "react";
import { createUserWithEmailAndPassword } from "firebase/auth";
import { auth } from "./firebase.js";
import { registrarPerfil } from "./api.js";
export default function Registro({ onVolver }) {
  const [mensaje, setMensaje] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [usuarioPendiente, setUsuarioPendiente] = useState(null);
  const [completado, setCompletado] = useState(false);

  async function handleRegistro(e) {
    e.preventDefault();

    const datos = new FormData(e.currentTarget);
    const nombres = datos.get("nombres").trim();
    const apellidos = datos.get("apellidos").trim();
    const correo = datos.get("correo").trim();

    if (!nombres || !apellidos) {
      setMensaje("Completa tus nombres y apellidos.");
      return;
    }

    setEnviando(true);
    setMensaje("Creando tu cuenta…");

    let usuario = usuarioPendiente;

    try {
      if (!usuario) {
        const resultado = await createUserWithEmailAndPassword(
          auth,
          correo,
          datos.get("contrasena"),
        );
        usuario = resultado.user;
        setUsuarioPendiente(usuario);
      }

      await registrarPerfil(usuario, {
        tipo_cuenta: "persona",
        nombre_mostrar: `${nombres} ${apellidos}`,
        datos_persona: {
          nombres,
          apellidos,
          fecha_nacimiento: datos.get("fechaNacimiento"),
        },
      });

      setCompletado(true);
      setMensaje("Cuenta creada correctamente. Ya puedes iniciar sesión.");
    } catch (error) {
      if (usuario) {
        setMensaje(
          `Firebase creó la cuenta, pero no se pudo guardar el perfil${error.status ? ` (HTTP ${error.status})` : ""}. Puedes reintentar desde aquí.`,
        );
      } else if (error.code === "auth/email-already-in-use") {
        setMensaje("Ese correo ya tiene una cuenta.");
      } else {
        setMensaje(
          "No pudimos crear la cuenta. Revisa los datos e inténtalo otra vez.",
        );
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-container">
        <h1>Crear una cuenta</h1>

        <form onSubmit={handleRegistro}>
          <div className="form-field">
            <label htmlFor="registro-nombres">Nombres</label>
            <input
              id="registro-nombres"
              name="nombres"
              autoComplete="given-name"
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="registro-apellidos">Apellidos</label>
            <input
              id="registro-apellidos"
              name="apellidos"
              autoComplete="family-name"
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="registro-fecha">Fecha de nacimiento</label>
            <input
              id="registro-fecha"
              name="fechaNacimiento"
              type="date"
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="registro-correo">Correo electrónico</label>
            <input
              id="registro-correo"
              name="correo"
              type="email"
              autoComplete="email"
              required
            />
          </div>

          <div className="form-field">
            <label htmlFor="registro-clave">Contraseña</label>
            <input
              id="registro-clave"
              name="contrasena"
              type="password"
              autoComplete="new-password"
              required
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={enviando || completado}
          >
            {enviando
              ? "Guardando…"
              : usuarioPendiente && !completado
                ? "Reintentar registro"
                : "Crear mi cuenta"}
          </button>

          {mensaje && <p role="status">{mensaje}</p>}

          <button
            type="button"
            className="btn-secondary"
            onClick={onVolver}
            disabled={enviando}
          >
            Volver a iniciar sesión
          </button>
        </form>
      </div>
    </main>
  );
}
