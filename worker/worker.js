// Atas — Worker Cloudflare
// - POST /api/upload : recebe a transcrição (Bearer token), resume com Workers AI,
//                      guarda no D1 e devolve o link da página.
// - GET  /r/<id>     : renderiza a página branded da ata (pública p/ quem tem o link).
// - GET  /           : landing simples.

const MARCA = "RYZE";                        // identidade visual RYZE
const SITE = "ryzecode.com.br";
const MODELO = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"; // 70B p/ resumo executivo mais rico

// Símbolo RYZE (seta ascendente). fill = cor; h = altura CSS (ex.: "34px").
const LOGO_PATH =
  "M308.484 282.06L244.072 357.593H211L231.18 392H350.77L400 520H244.159L171.652 352.605L177.931 342.661L225 254.736L211.896 226.997L191.439 180.558L159.957 267.483L127.315 354.301L112.868 394.729H139.992L194.254 520H0L200 0L308.484 282.06Z";
function logo(fill, h) {
  return `<svg viewBox="0 0 400 520" fill="none" xmlns="http://www.w3.org/2000/svg" style="height:${h};width:auto;display:block"><path d="${LOGO_PATH}" fill="${fill}"/></svg>`;
}

const ESQUEMA = {
  type: "object",
  properties: {
    contexto: { type: "string" },
    resumo_executivo: { type: "string" },
    temas: { type: "array", items: { type: "string" } },
    decisoes: { type: "array", items: { type: "string" } },
    proximos_passos: {
      type: "array",
      items: {
        type: "object",
        properties: {
          acao: { type: "string" },
          responsavel: { type: "string" },
          prazo: { type: "string" },
        },
        required: ["acao", "responsavel", "prazo"],
      },
    },
    pendencias: { type: "array", items: { type: "string" } },
  },
  required: ["resumo_executivo", "decisoes", "proximos_passos"],
};

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname;

    if (req.method === "POST" && path === "/api/upload") {
      return upload(req, env, url);
    }
    if (req.method === "GET" && path.startsWith("/r/")) {
      return verAta(path.slice(3), env);
    }
    if (req.method === "GET" && path === "/") {
      return html(landing(), 200);
    }
    return new Response("Não encontrado", { status: 404 });
  },
};

async function upload(req, env, url) {
  // Autenticação simples por token compartilhado.
  const auth = req.headers.get("Authorization") || "";
  if (!env.UPLOAD_TOKEN || auth !== `Bearer ${env.UPLOAD_TOKEN}`) {
    return Response.json({ erro: "não autorizado" }, { status: 401 });
  }

  let corpo;
  try {
    corpo = await req.json();
  } catch {
    return Response.json({ erro: "JSON inválido" }, { status: 400 });
  }
  const titulo = (corpo.titulo || "Reunião").toString().slice(0, 200);
  const segments = Array.isArray(corpo.segments) ? corpo.segments : [];

  // Monta o texto "Falante: fala" para o modelo.
  const transcricao = segments
    .map((s) => `${s.speaker}: ${s.text}`)
    .join("\n")
    .slice(0, 40000); // corta transcrições gigantes p/ caber no contexto

  let resumo = null;
  try {
    resumo = await resumir(env, transcricao);
  } catch (e) {
    // Se a IA falhar, ainda guardamos a transcrição — a página mostra sem resumo.
    resumo = null;
  }

  const id = crypto.randomUUID().replace(/-/g, "");
  const data = new Date().toISOString();
  await env.DB.prepare(
    "INSERT INTO reunioes (id, titulo, data, segments, resumo) VALUES (?, ?, ?, ?, ?)"
  )
    .bind(id, titulo, data, JSON.stringify(segments), resumo ? JSON.stringify(resumo) : null)
    .run();

  return Response.json({ url: `${url.origin}/r/${id}` });
}

async function resumir(env, transcricao) {
  const system =
    "Você é um analista que produz ATAS EXECUTIVAS de reuniões de negócios em português do Brasil. " +
    "Seja fiel ao conteúdo e NÃO invente fatos, mas seja específico e concreto: capture nomes, números, " +
    "valores, prazos, produtos e argumentos realmente ditos. Evite generalidades vagas. Responda SOMENTE com JSON válido.";
  const user =
    'Analise a reunião abaixo. "Você" é o consultor (RYZE); os demais são o(s) cliente(s), ' +
    'que podem aparecer como "Participante" ou, quando há vários, "Participante 1", "Participante 2" etc. ' +
    "Quando alguém disser o próprio nome ou for chamado pelo nome, use o nome real na atribuição.\n\n" +
    "Preencha os campos:\n" +
    "- contexto: 1-2 frases sobre o objetivo/assunto da reunião e quem participou (se identificável).\n" +
    "- resumo_executivo: 5 a 8 frases, densas e informativas — o que foi discutido, os encaminhamentos e o porquê.\n" +
    "- temas: os principais assuntos tratados (3 a 8 itens curtos).\n" +
    "- decisoes: tudo que ficou decidido (seja concreto).\n" +
    '- proximos_passos: itens com "acao", "responsavel" [Você/Participante/indefinido] e "prazo" [ou "não definido"].\n' +
    "- pendencias: pontos em aberto, dúvidas ou riscos a resolver (lista vazia se não houver).\n\n" +
    "TRANSCRIÇÃO:\n" +
    transcricao;

  const r = await env.AI.run(MODELO, {
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    response_format: { type: "json_schema", json_schema: ESQUEMA },
    max_tokens: 2048,
  });

  let data = r.response;
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      // fallback: extrai o objeto JSON de dentro de um texto
      const i = data.indexOf("{");
      const j = data.lastIndexOf("}");
      data = JSON.parse(data.slice(i, j + 1));
    }
  }
  return data;
}

async function verAta(id, env) {
  const row = await env.DB.prepare(
    "SELECT titulo, data, segments, resumo FROM reunioes WHERE id = ?"
  )
    .bind(id)
    .first();
  if (!row) return html(landing("Ata não encontrada."), 404);

  const segments = JSON.parse(row.segments || "[]");
  const resumo = row.resumo ? JSON.parse(row.resumo) : null;
  return html(pagina(row.titulo, row.data, segments, resumo), 200);
}

// ---------- helpers de renderização ----------

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function tempo(seg) {
  const s = Math.max(0, Math.floor(seg || 0));
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function dataBR(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("pt-BR", {
      dateStyle: "long",
      timeStyle: "short",
      timeZone: "America/Sao_Paulo", // corrige o +3h (antes renderizava em UTC)
    });
  } catch {
    return iso;
  }
}

function html(body, status) {
  return new Response(body, {
    status: status || 200,
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}

function pagina(titulo, data, segments, resumo) {
  const linhas = segments
    .map((s) => {
      const eu = s.speaker === "Você";
      return `<div class="fala ${eu ? "eu" : "outro"}">
        <div class="meta"><span class="quem">${esc(s.speaker)}</span><span class="ts">${tempo(s.start)}</span></div>
        <div class="txt">${esc(s.text)}</div>
      </div>`;
    })
    .join("\n");

  let blocoResumo = "";
  if (resumo) {
    const decisoes = (resumo.decisoes || [])
      .map((d) => `<li>${esc(d)}</li>`)
      .join("");
    const passos = (resumo.proximos_passos || [])
      .map((p) => {
        const r = esc(p.responsavel || "");
        const cls = /voc[eê]/i.test(r) ? "eu" : /particip/i.test(r) ? "outro" : "ind";
        return `<tr><td>${esc(p.acao)}</td><td><span class="chip ${cls}">${r || "—"}</span></td><td class="prazo">${esc(p.prazo)}</td></tr>`;
      })
      .join("");
    const temas = (resumo.temas || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
    const pendencias = (resumo.pendencias || []).map((p) => `<li>${esc(p)}</li>`).join("");
    const contexto = resumo.contexto ? `<p class="ctx">${esc(resumo.contexto)}</p>` : "";
    blocoResumo = `
      <section class="card destaque">
        <div class="kicker">Resumo Executivo</div>
        ${contexto}
        <p class="lead">${esc(resumo.resumo_executivo)}</p>
      </section>
      ${temas ? `<section class="card"><div class="kicker">Temas Discutidos</div><div class="tags">${temas}</div></section>` : ""}
      ${decisoes ? `<section class="card"><div class="kicker">Decisões</div><ul class="lista">${decisoes}</ul></section>` : ""}
      ${passos ? `<section class="card"><div class="kicker">Próximos Passos</div>
        <div class="tbl"><table><thead><tr><th>Ação</th><th>Responsável</th><th>Prazo</th></tr></thead>
        <tbody>${passos}</tbody></table></div></section>` : ""}
      ${pendencias ? `<section class="card"><div class="kicker">Pontos em Aberto</div><ul class="lista">${pendencias}</ul></section>` : ""}
    `;
  } else {
    blocoResumo = `<section class="card"><div class="kicker">Resumo</div><p class="aviso">Resumo por IA indisponível — transcrição completa abaixo.</p></section>`;
  }

  return `<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(titulo)} — ${esc(MARCA)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>${CSS}</style>
</head><body>
<div class="wrap">
  <header class="capa">
    <div class="mark-bg">${logo("#FFB700", "220px")}</div>
    <div class="capa-top">
      <span class="lg">${logo("#FFB700", "32px")}</span>
      <span class="wordmark">${esc(MARCA)}</span>
    </div>
    <div class="eyebrow">Ata de Reunião</div>
    <h1>${esc(titulo)}</h1>
    <div class="data">${esc(dataBR(data))}</div>
  </header>
  ${blocoResumo}
  <section class="card transc">
    <div class="kicker">Transcrição</div>
    <div class="nota">Falantes: <b>Você</b> (microfone) e <b>Participante</b> (áudio da chamada).</div>
    <div class="transcricao">${linhas || "<p>Sem falas reconhecidas.</p>"}</div>
  </section>
  <footer class="rodape">
    <span class="rlogo">${logo("#CC9200", "15px")}</span>
    <span>${esc(MARCA)} · ${esc(SITE)} · gerado localmente · áudio não armazenado</span>
  </footer>
</div>
</body></html>`;
}

function landing(msg) {
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(MARCA)} — Atas</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>${CSS}</style></head>
<body><div class="wrap">
<header class="capa">
  <div class="mark-bg">${logo("#FFB700", "220px")}</div>
  <div class="capa-top"><span class="lg">${logo("#FFB700", "32px")}</span><span class="wordmark">${esc(MARCA)}</span></div>
  <div class="eyebrow">Atas de Reunião</div>
</header>
<section class="card"><p class="lead">${esc(msg || "Sistema de atas. Cada reunião tem um link próprio.")}</p></section>
<footer class="rodape"><span class="rlogo">${logo("#CC9200", "15px")}</span><span>${esc(MARCA)} · ${esc(SITE)}</span></footer>
</div></body></html>`;
}

const CSS = `
:root{
  --gold:#FFB700; --gold-dark:#CC9200; --gold-soft:#FFF6DE;
  --purple:#6A28C9;
  --black:#0D0D0D; --g900:#1A1A1A; --g700:#404040; --g600:#525252;
  --g500:#6B6B6B; --g300:#B0B0B0; --g200:#D4D4D4; --g100:#EBEBEB; --g50:#F5F5F5;
  --white:#FAFAFA;
  --sans:'Plus Jakarta Sans',-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  --disp:'Space Grotesk',var(--sans);
  --mono:'JetBrains Mono',ui-monospace,Consolas,monospace;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:var(--g50);color:var(--black);
  font-family:var(--sans);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:28px 22px 12px}

/* ── Capa ── */
.capa{position:relative;overflow:hidden;background:var(--black);color:var(--white);
  border-radius:18px;padding:44px 44px 40px;margin-bottom:22px}
.capa .mark-bg{position:absolute;right:-34px;bottom:-52px;opacity:.07;pointer-events:none}
.capa-top{display:flex;align-items:center;gap:12px;margin-bottom:38px}
.capa-top .lg svg{display:block}
.wordmark{font-family:var(--disp);font-weight:700;letter-spacing:5px;font-size:16px;color:var(--white)}
.eyebrow{font-family:var(--mono);font-size:11px;font-weight:500;letter-spacing:3px;
  text-transform:uppercase;color:var(--gold);margin-bottom:14px}
.capa h1{font-family:var(--disp);font-weight:700;font-size:clamp(25px,4vw,38px);
  letter-spacing:-.5px;line-height:1.15;margin:0 0 12px;color:var(--white)}
.capa .data{font-family:var(--mono);font-size:12.5px;letter-spacing:1px;color:var(--g300)}

/* ── Cards ── */
.card{background:#fff;border:1px solid var(--g100);border-radius:14px;
  padding:26px 28px;margin:0 0 18px;break-inside:avoid}
.card.destaque{border-left:3px solid var(--gold)}
.kicker{font-family:var(--mono);font-size:10.5px;font-weight:500;letter-spacing:2.5px;
  text-transform:uppercase;color:var(--gold-dark);margin-bottom:15px;
  display:flex;align-items:center;gap:11px}
.kicker::before{content:'';width:22px;height:2px;background:var(--gold);flex:none}
.lead{font-size:16.5px;line-height:1.7;color:var(--g700);margin:0}
.ctx{font-size:13px;color:var(--g500);margin:0 0 14px;padding-bottom:13px;border-bottom:1px dashed var(--g200);line-height:1.6}
.tags{display:flex;flex-wrap:wrap;gap:8px}
.tag{font-size:12px;font-weight:600;color:var(--g700);background:var(--g50);border:1px solid var(--g100);padding:5px 11px;border-radius:20px}
.aviso{color:var(--g500);font-size:14px;margin:0}

/* ── Lista de decisões ── */
.lista{list-style:none;margin:0;padding:0}
.lista li{position:relative;padding:9px 0 9px 22px;border-bottom:1px solid var(--g100);
  font-size:14.5px;color:var(--g700);line-height:1.6}
.lista li:last-child{border-bottom:none}
.lista li::before{content:'';position:absolute;left:0;top:17px;width:12px;height:2px;background:var(--gold)}

/* ── Tabela de próximos passos ── */
.tbl{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead th{background:var(--black);color:var(--gold);font-family:var(--mono);font-size:10px;
  font-weight:500;letter-spacing:1.5px;text-transform:uppercase;padding:11px 12px;text-align:left}
thead th:first-child{border-top-left-radius:8px}
thead th:last-child{border-top-right-radius:8px}
tbody td{padding:12px;border-bottom:1px solid var(--g100);color:var(--g700);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
td.prazo{font-family:var(--mono);font-size:12px;color:var(--g600);white-space:nowrap}
.chip{display:inline-block;font-size:11px;font-weight:600;padding:3px 9px;border-radius:20px;white-space:nowrap}
.chip.eu{background:var(--gold-soft);color:var(--gold-dark)}
.chip.outro{background:#EEE6FB;color:var(--purple)}
.chip.ind{background:var(--g100);color:var(--g600)}

/* ── Transcrição (leve) ── */
.transc .nota{color:var(--g500);font-size:12.5px;margin-bottom:14px}
.transc .nota b{color:var(--g700)}
.transcricao{display:flex;flex-direction:column;gap:9px}
.fala{padding:9px 13px;border-radius:11px;max-width:88%}
.fala.eu{background:var(--gold-soft);align-self:flex-end}
.fala.outro{background:var(--g50);border:1px solid var(--g100);align-self:flex-start}
.fala .meta{display:flex;gap:8px;align-items:baseline;margin-bottom:2px}
.fala .quem{font-weight:600;font-size:12.5px;color:var(--g900)}
.fala .ts{font-family:var(--mono);color:var(--g500);font-size:10.5px}
.fala .txt{font-size:14px;color:var(--g700);line-height:1.55}

/* ── Rodapé ── */
.rodape{display:flex;align-items:center;gap:9px;padding:22px 4px 10px;
  color:var(--g500);font-size:11.5px;font-family:var(--mono);letter-spacing:.3px}
.rodape .rlogo svg{display:block;opacity:.8}

/* ── Impressão (PDF) ── */
@page{size:A4;margin:14mm}
@media print{
  body{background:#fff}
  .wrap{max-width:none;padding:0}
  .capa{border-radius:14px}
  .transc{break-before:page}
  .card{break-inside:avoid}
  .fala{break-inside:avoid}
}
`;
