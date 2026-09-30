// Testes do Worker com Miniflare (D1 local de verdade, SQLite). `npm test` em worker/.
// Cobrem o contrato que o lado local usa e as promessas de segurança da v2:
// token obrigatório, senha por ata, cookie que só abre aquela ata, expiração,
// exclusão, idempotência por chave e compatibilidade com as atas da v1.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Miniflare } from "miniflare";

const TOKEN = "token-de-teste";
const SENHA = "abcd-efgh";
let mf;
const BASE = "http://atas.test";

before(async () => {
  mf = new Miniflare({
    modules: true,
    scriptPath: new URL("../worker.js", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
    d1Databases: ["DB"],
    bindings: { UPLOAD_TOKEN: TOKEN },
  });
  const db = await mf.getD1Database("DB");
  for (const f of ["0001_inicial.sql", "0002_v2_publicacao.sql"]) {
    const sql = readFileSync(new URL(`../migrations/${f}`, import.meta.url), "utf8")
      .split("\n").map((l) => l.replace(/--.*$/, "")).join("\n");
    for (const stmt of sql.split(";").map((s) => s.trim()).filter(Boolean)) {
      await db.prepare(stmt).run();
    }
  }
  // uma ata da v1: html NULL, renderizada de segments + resumo
  await db.prepare("INSERT INTO reunioes (id, titulo, data, segments, resumo) VALUES (?, ?, ?, ?, ?)")
    .bind("a".repeat(32), "Ata antiga", "2026-08-01T12:00:00Z",
      JSON.stringify([{ speaker: "Você", start: 0, end: 1, text: "olá <b>x</b>" }]), null).run();
});

after(async () => mf && (await mf.dispose()));

const api = (metodo, caminho, corpo, token = TOKEN) =>
  mf.dispatchFetch(BASE + caminho, {
    method: metodo,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: corpo ? JSON.stringify(corpo) : undefined,
    redirect: "manual",
  });

async function aberta(id, senha = SENHA) {
  const r = await mf.dispatchFetch(`${BASE}/r/${id}`, {
    method: "POST", body: new URLSearchParams({ senha }), redirect: "manual" });
  const ck = (r.headers.get("set-cookie") || "").split(";")[0];
  return mf.dispatchFetch(`${BASE}/r/${id}`, { headers: { Cookie: ck } });
}

test("publicar sem senha é recusado (toda página nova tem senha)", async () => {
  const r = await api("POST", "/api/atas", { chave: "k-sem", html: "<p>x</p>" });
  assert.equal(r.status, 400);
});

test("cookie velho (emitido há mais de 30 dias) não abre", async () => {
  const { id } = await (await api("POST", "/api/atas", { chave: "k-velho", html: "<p>V</p>", senha: SENHA })).json();
  const ok = await mf.dispatchFetch(`${BASE}/r/${id}`, {
    method: "POST", body: new URLSearchParams({ senha: SENHA }), redirect: "manual" });
  const [emitido, sig] = ok.headers.get("set-cookie").split(";")[0].split("=")[1].split(".");
  const velho = String(Number(emitido) - 31 * 86400);
  const r = await mf.dispatchFetch(`${BASE}/r/${id}`, { headers: { Cookie: `ata_${id}=${velho}.${sig}` } });
  assert.equal(r.status, 401, "trocar a data do cookie invalida a assinatura; cookie velho não passa");
});

test("API sem token é recusada", async () => {
  const r = await api("POST", "/api/atas", { chave: "x", html: "<p>x</p>" }, "errado");
  assert.equal(r.status, 401);
});

test("publica com senha: sem cookie pede senha, senha errada recusa, certa abre", async () => {
  const r = await api("POST", "/api/atas", {
    chave: "2026-09-30_1400_teste", titulo: "Teste", html: "<p>CONTEUDO-SECRETO</p>",
    senha: "abcd-efgh", expira_dias: 90,
  });
  assert.equal(r.status, 200);
  const { id, url, expira_em } = await r.json();
  assert.match(id, /^[0-9a-f]{32}$/);
  assert.ok(url.endsWith(`/r/${id}`));
  assert.ok(expira_em);

  const semSenha = await mf.dispatchFetch(`${BASE}/r/${id}`);
  assert.equal(semSenha.status, 401);
  assert.ok(!(await semSenha.text()).includes("CONTEUDO-SECRETO"));
  assert.equal(semSenha.headers.get("x-robots-tag"), "noindex, nofollow");

  const errada = await mf.dispatchFetch(`${BASE}/r/${id}`, {
    method: "POST", body: new URLSearchParams({ senha: "zzzz-zzzz" }), redirect: "manual" });
  assert.equal(errada.status, 401);

  const certa = await mf.dispatchFetch(`${BASE}/r/${id}`, {
    method: "POST", body: new URLSearchParams({ senha: " ABCD-EFGH " }), redirect: "manual" });
  assert.equal(certa.status, 303);
  const ck = certa.headers.get("set-cookie").split(";")[0];
  assert.ok(certa.headers.get("set-cookie").includes(`Path=/r/${id}`));

  const aberta = await mf.dispatchFetch(`${BASE}/r/${id}`, { headers: { Cookie: ck } });
  assert.equal(aberta.status, 200);
  assert.ok((await aberta.text()).includes("CONTEUDO-SECRETO"));
  assert.ok(aberta.headers.get("content-security-policy").includes("default-src 'none'"));
});

test("republicar a mesma chave atualiza a mesma página", async () => {
  const a = await (await api("POST", "/api/atas", { chave: "k-idem", titulo: "v1", html: "<p>v1</p>", senha: SENHA })).json();
  const b = await (await api("POST", "/api/atas", { chave: "k-idem", titulo: "v2", html: "<p>v2</p>", senha: SENHA })).json();
  assert.equal(a.id, b.id);
  assert.equal(b.atualizada, true);
  const t = await (await aberta(b.id)).text();
  assert.ok(t.includes("v2"));
});

test("cookie de uma ata não abre outra", async () => {
  const a = await (await api("POST", "/api/atas", { chave: "k-a", html: "<p>A</p>", senha: "aaaa-aaaa" })).json();
  const b = await (await api("POST", "/api/atas", { chave: "k-b", html: "<p>B</p>", senha: "aaaa-aaaa" })).json();
  const ok = await mf.dispatchFetch(`${BASE}/r/${a.id}`, {
    method: "POST", body: new URLSearchParams({ senha: "aaaa-aaaa" }), redirect: "manual" });
  const valor = ok.headers.get("set-cookie").split(";")[0].split("=")[1];
  const r = await mf.dispatchFetch(`${BASE}/r/${b.id}`, { headers: { Cookie: `ata_${b.id}=${valor}` } });
  assert.equal(r.status, 401);
});

test("exclusão e listagem", async () => {
  const { id } = await (await api("POST", "/api/atas", { chave: "k-del", html: "<p>x</p>", senha: SENHA })).json();
  const lista = await (await api("GET", "/api/atas")).json();
  assert.ok(lista.atas.some((x) => x.id === id));
  const del = await (await api("DELETE", `/api/atas/${id}`)).json();
  assert.equal(del.apagada, true);
  assert.equal((await mf.dispatchFetch(`${BASE}/r/${id}`)).status, 404);
});

test("expirada some (na leitura e no cron)", async () => {
  const db = await mf.getD1Database("DB");
  const { id } = await (await api("POST", "/api/atas", { chave: "k-exp", html: "<p>x</p>", senha: SENHA })).json();
  await db.prepare("UPDATE reunioes SET expira_em = '2000-01-01T00:00:00Z' WHERE id = ?").bind(id).run();
  assert.equal((await mf.dispatchFetch(`${BASE}/r/${id}`)).status, 404);
  const row = await db.prepare("SELECT id FROM reunioes WHERE id = ?").bind(id).first();
  assert.equal(row, null);

  const { id: id2 } = await (await api("POST", "/api/atas", { chave: "k-exp2", html: "<p>x</p>", senha: SENHA })).json();
  await db.prepare("UPDATE reunioes SET expira_em = '2000-01-01T00:00:00Z' WHERE id = ?").bind(id2).run();
  const w = await mf.getWorker();
  await w.scheduled({ cron: "17 9 * * *" });
  assert.equal(await db.prepare("SELECT id FROM reunioes WHERE id = ?").bind(id2).first(), null);
});

test("PATCH protege uma ata antiga com senha", async () => {
  const id = "a".repeat(32);
  const aberta = await mf.dispatchFetch(`${BASE}/r/${id}`);
  assert.equal(aberta.status, 200);
  const t = await aberta.text();
  assert.ok(t.includes("Ata antiga"));
  assert.ok(!t.includes("<b>x</b>"), "transcrição da v1 continua escapada");
  await api("PATCH", `/api/atas/${id}`, { senha: "bbbb-bbbb", expira_dias: 30 });
  assert.equal((await mf.dispatchFetch(`${BASE}/r/${id}`)).status, 401);
});

test("id malformado e rota desconhecida", async () => {
  assert.equal((await mf.dispatchFetch(`${BASE}/r/../../etc`)).status, 404);
  assert.equal((await mf.dispatchFetch(`${BASE}/nada`)).status, 404);
});
