const campoBusca = document.getElementById("campo-busca");
const resultadoBusca = document.getElementById("resultado-busca");

function iconeResultado(tipo) {
  if (tipo === "ministro") {
    return "Ministro";
  }
  if (tipo === "missa") {
    return "Missa";
  }
  if (tipo === "aviso") {
    return "Aviso";
  }
  return "Item";
}

if (campoBusca && resultadoBusca) {
  campoBusca.addEventListener("keyup", async function aoDigitar() {
    const termo = this.value.trim();

    if (termo.length < 2) {
      resultadoBusca.innerHTML = "";
      return;
    }

    try {
      const response = await fetch(`/api/busca?q=${encodeURIComponent(termo)}`);
      const data = await response.json();

      resultadoBusca.innerHTML = "";

      data.resultados.forEach((item) => {
        const linha = document.createElement("a");
        linha.className = "list-group-item list-group-item-action";
        linha.textContent = `${iconeResultado(item.tipo)}: ${item.texto}`;
        linha.href = item.url || "#";
        resultadoBusca.appendChild(linha);
      });
    } catch (error) {
      console.error("Falha na busca global:", error);
    }
  });
}
