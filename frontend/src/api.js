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