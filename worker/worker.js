/**
 * Atas — Worker Cloudflare (arquivo único, sem build e sem dependência de runtime).
 *
 * v2 (30/09/2026): o Worker virou só PUBLICADOR. Resumo e página são feitos na
 * máquina do Pedro (Claude + render.py); aqui só chega o entregável de reunião de
 * CLIENTE, já em HTML. Reunião interna (Parresia, carreira, pessoal) não sobe.
 *
 *  - POST   /api/atas        (Bearer) guarda/atualiza {chave, titulo, html, senha, expira_dias}
 *  - GET    /api/atas        (Bearer) lista o que está publicado
 *  - PATCH  /api/atas/<id>   (Bearer) troca senha e/ou expiração (serve às atas antigas)
 *  - DELETE /api/atas/<id>   (Bearer) apaga
 *  - GET    /r/<id>          página; se tiver senha, pede a senha antes
 *  - POST   /r/<id>          confere a senha e grava um cookie só daquela ata
 *  - GET    /                landing
 *  - cron diário             apaga o que expirou
 *
 * Atas publicadas antes da v2 (coluna html vazia) continuam renderizando pelo
 * código antigo, no fim deste arquivo, a partir de segments + resumo.
 *
 * Bindings (wrangler.toml): DB (D1). Segredo: UPLOAD_TOKEN.
 */

const MARCA = "RYZE";
const SITE = "ryzecode.com.br";
const MAX_HTML = 1_800_000; // D1 guarda até ~2 MB por linha

const LOGO_PATH =
  "M308.484 282.06L244.072 357.593H211L231.18 392H350.77L400 520H244.159L171.652 352.605L177.931 342.661L225 254.736L211.896 226.997L191.439 180.558L159.957 267.483L127.315 354.301L112.868 394.729H139.992L194.254 520H0L200 0L308.484 282.06Z";
function logo(fill, h) {
  return `<svg viewBox="0 0 400 520" fill="none" xmlns="http://www.w3.org/2000/svg" style="height:${h};width:auto;display:block"><path d="${LOGO_PATH}" fill="${fill}"/></svg>`;
}

// A página não tem script nenhum; a CSP garante que continue assim mesmo que um
// texto de transcrição mal escapado tente injetar algum.
const CABECALHOS_PAGINA = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Robots-Tag": "noindex, nofollow",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy":
    "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; " +
    "font-src https://fonts.gstatic.com; img-src data:; form-action 'self'; frame-ancestors 'none'",
};

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const path = url.pathname;
    try {
      if (path === "/api/atas" || path.startsWith("/api/atas/")) {
        if (!autorizado(req, env)) return Response.json({ erro: "não autorizado" }, { status: 401 });
        const id = path.slice("/api/atas/".length);
        if (req.method === "POST" && path === "/api/atas") return publicar(req, env, url);
        if (req.method === "GET" && path === "/api/atas") return listar(env);
        if (req.method === "PATCH" && id) return alterar(req, env, id);
        if (req.method === "DELETE" && id) return apagar(env, id);
        return Response.json({ erro: "método não suportado" }, { status: 405 });
      }
      if (path.startsWith("/r/")) {
        const id = path.slice(3);
        if (req.method === "GET") return verAta(req, env, id);
        if (req.method === "POST") return entrar(req, env, id);
      }
      if (req.method === "GET" && path === "/") return pagina200(landing());
      return new Response("Não encontrado", { status: 404 });
    } catch (e) {
      // Nada de falha silenciosa: o motivo vai para o log (wrangler tail) e para
      // quem chamou a API; a página pública só diz que deu erro.
      console.error("erro", path, e && e.stack ? e.stack : e);
      if (path.startsWith("/api/")) return Response.json({ erro: String(e) }, { status: 500 });
      return new Response("Erro interno", { status: 500 });
    }
  },

  async scheduled(_evt, env) {
    const r = await env.DB.prepare(
      "DELETE FROM reunioes WHERE expira_em IS NOT NULL AND expira_em < ?"
    ).bind(new Date().toISOString()).run();
    console.log("retenção: apagadas", r.meta && r.meta.changes);
  },
};

function autorizado(req, env) {
  const auth = req.headers.get("Authorization") || "";
  return Boolean(env.UPLOAD_TOKEN) && iguais(auth, `Bearer ${env.UPLOAD_TOKEN}`);
}

// ---------- API ----------

async function publicar(req, env, url) {
  let c;
  try {
    c = await req.json();
  } catch {
    return Response.json({ erro: "JSON inválido" }, { status: 400 });
  }
  const chave = String(c.chave || "").slice(0, 120);
  const titulo = String(c.titulo || "Reunião").slice(0, 200);
  const html = String(c.html || "");
  if (!chave || !html) return Response.json({ erro: "faltam chave e html" }, { status: 400 });
  // v2: toda página nova tem senha. Página aberta só existe como legado da v1.
  if (!c.senha || String(c.senha).trim().length < 8)
    return Response.json({ erro: "senha obrigatória (8+ caracteres)" }, { status: 400 });
  if (html.length > MAX_HTML) return Response.json({ erro: "html grande demais" }, { status: 413 });
  const expira = expiracao(c.expira_dias);
  const { hash, sal } = c.senha ? await hashSenha(String(c.senha)) : { hash: null, sal: null };

  // idempotente por chave: republicar a mesma reunião atualiza a mesma página
  const existente = await env.DB.prepare("SELECT id FROM reunioes WHERE chave = ?").bind(chave).first();
  const id = existente ? existente.id : crypto.randomUUID().replace(/-/g, "");
  if (existente) {
    await env.DB.prepare(
      "UPDATE reunioes SET titulo=?, html=?, senha_hash=?, senha_sal=?, expira_em=? WHERE id=?"
    ).bind(titulo, html, hash, sal, expira, id).run();
  } else {
    await env.DB.prepare(
      "INSERT INTO reunioes (id, titulo, data, segments, resumo, chave, html, senha_hash, senha_sal, expira_em) " +
        "VALUES (?, ?, ?, '[]', NULL, ?, ?, ?, ?, ?)"
    ).bind(id, titulo, new Date().toISOString(), chave, html, hash, sal, expira).run();
  }
  return Response.json({ id, url: `${url.origin}/r/${id}`, expira_em: expira, atualizada: !!existente });
}

async function listar(env) {
  const r = await env.DB.prepare(
    "SELECT id, titulo, data, chave, expira_em, senha_hash IS NOT NULL AS tem_senha, " +
      "html IS NULL AS legado FROM reunioes ORDER BY data DESC"
  ).all();
  return Response.json({ atas: r.results || [] });
}

async function alterar(req, env, id) {
  let c;
  try {
    c = await req.json();
  } catch {
    return Response.json({ erro: "JSON inválido" }, { status: 400 });
  }
  const row = await env.DB.prepare("SELECT id FROM reunioes WHERE id = ?").bind(id).first();
  if (!row) return Response.json({ erro: "não encontrada" }, { status: 404 });
  if ("senha" in c) {
    const { hash, sal } = c.senha ? await hashSenha(String(c.senha)) : { hash: null, sal: null };
    await env.DB.prepare("UPDATE reunioes SET senha_hash=?, senha_sal=? WHERE id=?").bind(hash, sal, id).run();
  }
  if ("expira_dias" in c) {
    await env.DB.prepare("UPDATE reunioes SET expira_em=? WHERE id=?").bind(expiracao(c.expira_dias), id).run();
  }
  return Response.json({ ok: true });
}

async function apagar(env, id) {
  const r = await env.DB.prepare("DELETE FROM reunioes WHERE id = ?").bind(id).run();
  return Response.json({ apagada: (r.meta && r.meta.changes) > 0 });
}

function expiracao(dias) {
  const n = Number(dias || 0);
  if (!n || n <= 0) return null;
  return new Date(Date.now() + n * 86400000).toISOString();
}

// ---------- senha ----------
// A senha é aleatória (8 caracteres de um alfabeto de 31 ≈ 40 bits), gerada na
// máquina do Pedro; o risco é adivinhação online, não quebra de hash. SHA-256 com
// sal basta e cabe no limite de CPU do plano gratuito (PBKDF2 não caberia).

async function sha256hex(txt) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(txt));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

async function hashSenha(senha, sal) {
  sal = sal || crypto.randomUUID().replace(/-/g, "");
  return { hash: await sha256hex(`${sal}:${senha.trim().toLowerCase()}`), sal };
}

const COOKIE_DIAS = 30;

async function assinatura(env, id, hash, emitido) {
  const k = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(env.UPLOAD_TOKEN || ""), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const s = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(`${id}:${hash}:${emitido}`));
  return [...new Uint8Array(s)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

// cookie = "<emitido_em_segundos>.<hmac(id:hash:emitido)>": a validade é conferida AQUI,
// não só pelo Max-Age do navegador; trocar a senha invalida todos os cookies da ata.
async function cookieValido(req, env, id, hash) {
  const v = cookie(req, `ata_${id}`) || "";
  const i = v.indexOf(".");
  if (i < 1) return false;
  const emitido = v.slice(0, i);
  const idade = Date.now() / 1000 - Number(emitido);
  if (!(idade >= 0 && idade <= COOKIE_DIAS * 86400)) return false;
  return iguais(v.slice(i + 1), await assinatura(env, id, hash, emitido));
}

function cookie(req, nome) {
  const c = req.headers.get("Cookie") || "";
  for (const parte of c.split(/;\s*/)) {
    const i = parte.indexOf("=");
    if (i > 0 && parte.slice(0, i) === nome) return parte.slice(i + 1);
  }
  return null;
}

function iguais(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

// ---------- páginas ----------

async function buscar(env, id) {
  if (!/^[0-9a-f]{32}$/.test(id)) return null;
  const row = await env.DB.prepare(
    "SELECT id, titulo, data, segments, resumo, html, senha_hash, senha_sal, expira_em FROM reunioes WHERE id = ?"
  ).bind(id).first();
  if (!row) return null;
  if (row.expira_em && row.expira_em < new Date().toISOString()) {
    await env.DB.prepare("DELETE FROM reunioes WHERE id = ?").bind(id).run();
    return null;
  }
  return row;
}

async function verAta(req, env, id) {
  const row = await buscar(env, id);
  if (!row) return html(landing("Ata não encontrada ou expirada."), 404);
  if (row.senha_hash) {
    if (!(await cookieValido(req, env, id, row.senha_hash))) return html(formSenha(row.titulo), 401);
  }
  if (row.html) return pagina200(row.html);
  const segments = JSON.parse(row.segments || "[]");
  const resumo = row.resumo ? JSON.parse(row.resumo) : null;
  return pagina200(pagina(row.titulo, row.data, segments, resumo));
}

async function entrar(req, env, id) {
  const row = await buscar(env, id);
  if (!row) return html(landing("Ata não encontrada ou expirada."), 404);
  if (!row.senha_hash) return Response.redirect(new URL(`/r/${id}`, req.url).toString(), 303);
  const form = await req.formData().catch(() => null);
  const senha = form ? String(form.get("senha") || "") : "";
  const { hash } = await hashSenha(senha, row.senha_sal);
  if (!iguais(hash, row.senha_hash)) {
    await new Promise((r) => setTimeout(r, 400)); // freio barato contra tentativa em massa
    return html(formSenha(row.titulo, "Senha incorreta."), 401);
  }
  const emitido = String(Math.floor(Date.now() / 1000));
  const sig = await assinatura(env, id, row.senha_hash, emitido);
  return new Response(null, {
    status: 303,
    headers: {
      Location: `/r/${id}`,
      "Set-Cookie": `ata_${id}=${emitido}.${sig}; Path=/r/${id}; Max-Age=${COOKIE_DIAS * 86400}; HttpOnly; Secure; SameSite=Lax`,
      "Cache-Control": "no-store",
    },
  });
}

function pagina200(body) {
  return new Response(body, { status: 200, headers: CABECALHOS_PAGINA });
}

function html(body, status) {
  return new Response(body, { status: status || 200, headers: CABECALHOS_PAGINA });
}

function formSenha(titulo, erro) {
  return `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>${esc(MARCA)} — Ata</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>${CSS}
.senha{max-width:420px;margin:0 auto}
.senha form{display:flex;flex-direction:column;gap:12px;margin-top:18px}
.senha input{font:inherit;font-size:18px;padding:12px 14px;border:1px solid var(--g200);border-radius:10px;letter-spacing:2px}
.senha button{font:inherit;font-weight:600;padding:12px;border:0;border-radius:10px;background:var(--black);color:var(--gold);cursor:pointer}
.senha .erro{color:#B4552D;font-size:14px;margin:0}
</style></head><body><div class="wrap senha">
<header class="capa"><div class="capa-top"><span class="lg">${logo("#FFB700", "30px")}</span><span class="wordmark">${esc(MARCA)}</span></div>
<div class="eyebrow">Ata de reunião</div><h1>${esc(titulo)}</h1></header>
<section class="card"><p class="lead">Esta ata é protegida. Digite a senha que você recebeu junto com o link.</p>
${erro ? `<p class="erro">${esc(erro)}</p>` : ""}
<form method="post"><input name="senha" autocomplete="off" autofocus aria-label="Senha" placeholder="xxxx-xxxx"><button type="submit">Abrir a ata</button></form></section>
</div></body></html>`;
}

// ---------- legado: atas publicadas antes da v2 (html vazio) ----------
// Renderiza a partir de segments + resumo, como a v1 fazia. Nada novo passa por aqui.

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

/* ── Impressão (PDF) ──
   Não é enfeite: é este bloco que o Chrome headless do entregavel.py usa para
   imprimir o arquivo que vai ao cliente. A transcrição começa em página nova e
   nenhum card é partido no meio. */
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
