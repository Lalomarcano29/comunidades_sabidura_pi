export default function Perfil({ perfil }) {
  const nombre = perfil.nombre_mostrar;
  const foto = perfil.foto_perfil?.url;
  const biografia = perfil.biografia?.trim();

  return (
    <main className="login-page">
      <div className="login-container">
        <h1>Mi perfil</h1>

        {foto ? (
          <img src={foto} alt={`Foto de perfil de ${nombre}`} width={112} />
        ) : (
          <p>Sin fotografía de perfil</p>
        )}

        <h2>{nombre}</h2>

        <h3>Biografía</h3>
        <p>{biografia || "Aún no hay una biografía."}</p>
      </div>
    </main>
  );
}