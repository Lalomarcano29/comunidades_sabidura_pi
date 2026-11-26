export async function obtenerMiPerfil(usuarioFirebase) {
  const token = await usuarioFirebase.getIdToken();

  const respuesta = await fetch("http://127.0.0.1:8000/api/perfil/", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!respuesta.ok) {
    throw new Error(`Django respondió con el estado ${respuesta.status}.`);
  }

  return respuesta.json();
}
export async function registrarPerfil(usuarioFirebase, datosPerfil) {
  const token = await usuarioFirebase.getIdToken();

  const respuesta = await fetch("http://127.0.0.1:8000/api/auth/registro/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(datosPerfil),
  });

  if (!respuesta.ok) {
    const error = new Error(`Django respondió con HTTP ${respuesta.status}.`);
    error.status = respuesta.status;
    throw error;
  }

  return respuesta.json();
}