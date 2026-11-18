import { useState } from "react";
import "./App.css";

function App() {
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [mensaje, setMensaje] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!correo.trim() || !contrasena.trim()) {
      setMensaje("Debes completar todos los campos.");
      return;
    }

    setMensaje(
      "Formulario completado. La conexión con el servidor está pendiente."
    );
  };

  return (
    <main className="login-page">
      <div className="login-container">
        <header className="app-header">
          <div className="app-logo" aria-hidden="true">
            <span>♣</span>
          </div>

          <div className="app-brand">
            Comunidades
            <br />
            de Sabiduría
          </div>
        </header>

        <div
          className="login-banner"
          role="img"
          aria-label="Ilustración de plantas creciendo bajo el sol"
        >
          <svg viewBox="0 0 440 112" preserveAspectRatio="xMidYMid slice">
            <rect width="440" height="112" fill="#deebdd" />
            <circle cx="370" cy="26" r="39" fill="#f1bf74" />

            <path
              d="M0 90 Q120 55 210 87 T440 64 V112 H0Z"
              fill="#91b091"
            />
            <path
              d="M0 112 Q105 79 205 107 T440 93 V112Z"
              fill="#386d53"
            />

            <g stroke="#205a42" strokeWidth="4" fill="#205a42">
              <path d="M110 104 V43" />
              <path d="M110 68 Q75 65 68 38 Q101 37 110 68" />
              <path d="M110 48 Q119 18 150 20 Q147 47 110 48" />

              <path d="M218 104 V64" />
              <path d="M218 78 Q188 72 185 52 Q210 51 218 78" />
              <path d="M218 67 Q229 44 254 44 Q247 66 218 67" />
            </g>

            <path
              d="M20 108 L85 96 M290 108 L360 94"
              stroke="#f7f4ec"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
        </div>

        <h1>Iniciar sesión</h1>
        <p className="login-subtitle">Accede a tu comunidad.</p>

        <form onSubmit={handleSubmit} noValidate>
          <div className="form-field">
            <label htmlFor="correo">Correo o teléfono</label>
            <input
              id="correo"
              type="text"
              placeholder="nombre@correo.cl"
              autoComplete="username"
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label htmlFor="contrasena">Contraseña</label>
            <input
              id="contrasena"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              value={contrasena}
              onChange={(e) => setContrasena(e.target.value)}
            />
          </div>

          {mensaje && (
            <p className="form-message" role="status">
              {mensaje}
            </p>
          )}

          <button type="submit" className="btn-primary">
            Iniciar sesión
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() =>
              setMensaje(
                "La pantalla de registro se implementará a continuación."
              )
            }
          >
            Crear una cuenta
          </button>
        </form>
      </div>
    </main>
  );
}

export default App;
