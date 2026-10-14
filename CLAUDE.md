# CLAUDE.md — atas

Gravador de reunião do Pedro: grava no disco enquanto a reunião acontece, transcreve local
(faster-whisper na GPU), separa falantes e o Claude monta uma ata estruturada e auditada
(`ata.json`). Só reunião de **cliente** sai da máquina (PDF RYZE e página com senha no Worker).

## Onde está a arquitetura

- `README.md` — uso diário, CLI, testes, montar do zero.
- `docs/ARQUITETURA.md` — fonte da verdade: pipeline (§4), venvs (§5), falantes (§6), ata (§7),
  dados e retenção (§8), Worker (§10), **receitas (§11)**, /ata (§12), **armadilhas (§14)**,
  Raio-X calibrado (§17). Não copiar daqui: ler lá.
- `docs/MELHORIAS.md` — backlog e status por item. `docs/BRIEFING-V2.md` — requisitos R1–R9.
- Skill `/ata`: `claude/skills/ata/SKILL.md` (junction em `~/.claude/skills/ata`).

## Rodar e testar (sempre com o Python do venv, nunca o do PATH)

```powershell
# testes Python — README.md:61, tests/conftest.py:4
C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe -m pytest tests -q
# pular os lentos (Whisper/Chrome/dispositivo real) — tests/conftest.py:5
C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe -m pytest tests -q -m "not lento"
# testes do Worker (Miniflare) — README.md:62, worker/package.json:7
cd worker; npm test
```

CLI (README.md:51-57):

```powershell
$A = "C:\Users\olive\.venvs\faster-whisper\Scripts\python.exe C:\Users\olive\Projetos\atas\local\atas.py"
Invoke-Expression "$A listar"
Invoke-Expression "$A mostrar ultima"
Invoke-Expression "$A --help"
```

Demais comandos (`processar`, `falantes`, `confirmar`, `publicar`, `tipo`, `fala`, `calibrar`…)
estão em `docs/ARQUITETURA.md` §11. `diarize.py` roda no venv `C:\Users\olive\.venvs\diar`,
não no principal (§5 e §14).

## Estado que muda o que você faz

- **Worker v2 não está no ar** (registrado em `docs/MELHORIAS.md:26` e `:119`; testado só local):
  o login padrão do wrangler desta máquina é a conta pessoal (`docs/ARQUITETURA.md` §14). O
  `wrangler.toml` tem `account_id` fixo, então deploy com o login errado falha. Antes de afirmar
  que algo foi publicado, conferir com `npx wrangler deployments list` (§11, linha 371).
- Deploy em produção, na ordem de `docs/ARQUITETURA.md:371`: `npm test` →
  `npx wrangler deployments list` → `npx wrangler d1 migrations apply atas --remote` →
  `npx wrangler deploy`. Só com o OK do Pedro.

## Regras do Pedro (não negociáveis)

1. **Publicação nunca é automática.** O Claude propõe; o Pedro aprova na hora, a cada vez.
   Vale para página do cliente (`publicar <id>`), ClickUp, memória, Sinapse e log de decisões.
   OK de uma reunião não vale para a próxima (skill `/ata`, regra 1).
2. **Só as falas rotuladas "Você" são do Pedro.** "Participante N" é o áudio da chamada e a
   diarização erra; tarefa sem dono confirmado não vira tarefa do Pedro.
3. **Nada inventado.** Item sem citação achada é suspeito, não fato; prazo não dito é lacuna.
4. **Métrica vem com leitura, nunca só o dado** (o que é, faixa, onde ele ficou, o que fazer).
   Vale para Raio-X, voz e qualquer número que o Pedro vá ler.
5. **Avaliação interna nunca vai ao cliente** (`avaliacao-interna*.md` fica na pasta da sessão).
   Ela confere as afirmações do Pedro, **erradas primeiro**, e só chama de errado o que foi
   conferido (código, memória, número medido); valores contra o piso de hora; negociação;
   postura com números do Raio-X.
6. **Parresia fora do Sinapse.** Tipo `parresia` vai para
   `~/Projetos/qa-parresia/rotinas/decisoes.jsonl`. A única escrita automática no vault é
   `08-CRESCIMENTO/fala-raio-x.md` (etapa `raio_x`, sem título de reunião).
7. **ClickUp só pelos wrappers com o token dele** (`~/Projetos/qa-parresia/scripts`), nunca
   pelo MCP.
8. **Credencial nunca no chat nem em arquivo versionado.** Senha da página fica no
   `sessao.json`; diga onde está, não imprima.

## Dados fora do git (LGPD) — `.gitignore`

`local/config.json` (segredos), `atas-salvas/`, `fala-analise/`, `local/out/`, `local/models/`.
Nunca forçar esses caminhos para dentro de um commit.

## Armadilhas (detalhe em `docs/ARQUITETURA.md` §14)

- Gravação se testa com **dispositivo real** na mesma sequência de threads da janela: o falso
  não pega o erro de COM (`tests/test_dispositivos_reais.py`, lento).
- Não tirar o `word_timestamps` do turbo com vocabulário.
- `os.replace` no Windows falha com leitor aberto; `sessao.json` já tem lock e retentativa.
- **Escape em script gerado por script** (§14): `\b`/`\x00` viraram caractere de controle.
  Patch com regex ou contrabarra vai por **Write/Edit**, nunca `node -e`/`python -` inline no
  Bash (o Git Bash come as contrabarras e pode gerar código válido e errado).
- Python do PATH é stub da Store; transcrição só no venv `faster-whisper`.

## Commits e hooks

- Mensagens em **português**, **sem** trailer `Co-Authored-By` e sem "Generated with Claude
  Code" (sobrepõe o default do harness).
- Hook de segredos: o pre-commit global de gitleaks (`C:\Users\olive\.git-hooks\pre-commit`,
  via `core.hooksPath` global) roda antes do commit e encadeia o hook do repo. **Nunca usar
  `--no-verify`**; se ele barrar, tire o segredo, não o hook.
- Fluxo: revisão → commit/push (e deploy, quando houver e ele aprovar) → o Claude registra no
  Sinapse o que for conhecimento/projeto.

## Como relatar

Três estados, nunca dois: **por relato · verificado por medição/teste · não feito**. "Testado
no Miniflare" não é "no ar"; "commitado" não é "deployado".
