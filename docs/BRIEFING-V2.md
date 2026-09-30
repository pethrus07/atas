# Atas v2 — briefing para a próxima sessão

> **Prioridade 01 do Pedro (30/09/2026).** O Atas deixa de ser "gravador de reunião de cliente" e
> vira **o registro oficial de toda reunião importante** — inclusive as da nova fase dele como PO
> na Parresia. Tem de ficar **muito bom, completo e integrado** com o Claude, com o Sinapse e com o
> resto do ecossistema.
>
> Este documento é o ponto de partida de uma sessão nova. Leia-o inteiro, depois
> [`ARQUITETURA.md`](ARQUITETURA.md) (o funcionamento atual, 436 linhas), e só então proponha.

---

## 1 · Por que agora

- **A conversa mais importante do mês se perdeu.** ~20/09/2026 o Pedro gravou a conversa com o
  Mauro (CEO da Parresia) sobre a ida dele para PO; o PC travou no meio e **não sobrou nada**:
  `record.py` acumula o áudio em memória e só escreve `mic.wav`/`loopback.wav` no fim, e
  `local/out/` estava vazio. Reunião importante não pode depender de o processo terminar bem.
- **Como PO, reunião vira o principal insumo de trabalho.** Decisão, encaminhamento com dono e
  data, pergunta em aberto — tudo nasce em reunião. Hoje isso sai como prosa de um Llama 70B e
  morre numa página; ninguém (nem o Claude) consome de forma estruturada.
- **O diarizador está quebrado na prática.** Um participante remoto virou **78 "Participantes"**
  (08/09); por isso, em 09/09, tarefas de uma terceira pessoa foram atribuídas ao Pedro.
  Enquanto isso não fechar, "Participante" é um saco de várias pessoas.

## 2 · Estado atual (conferido em 30/09/2026)

| Área | Estado |
|---|---|
| Repo | `pethrus07/atas` (privado), `main` limpo e sincronizado; último commit `c18ca0b` (docs) |
| Captura | `soundcard`, mic = "Você" + loopback WASAPI = "Participante"; fallback de dispositivo (bug do mic USB AB13X, 03/09) |
| Transcrição | faster-whisper `small`, **CPU/int8**, 2 passadas, pt — ⚠️ a máquina tem **RTX 3050 Ti (4 GB)**, nunca usada |
| Diarização | sherpa-onnx no venv `diar` (py3.12) via subprocess; `config.json` **não tem** `diar_threshold`/`diar_num_speakers` → vale o padrão 0.5, que fatia |
| Resumo | Worker `atas` (Cloudflare, conta ryzecode08) → Workers AI `llama-3.3-70b`, só os primeiros **40 000 caracteres**; falha é silenciosa |
| Página/PDF | `/r/<id>` com a marca RYZE; `entregavel.py` baixa e gera PDF via Chrome headless; **sem upload não há PDF** |
| Raio-X da Fala | `analise_fala.py` → `fala-analise/` + nota auto `sinapse/08-CRESCIMENTO/fala-raio-x.md` |
| Dados | 27 atas em `atas-salvas/` (.md/.html/.pdf); texto no D1 **sem prazo e sem rota de exclusão** |
| Segurança | link público-não-adivinhável; **senha por reunião não existe**; domínio próprio adiado |
| Testes | **nenhum**, em nenhum dos lados; deploy do Worker vai direto para produção |
| Ideia registrada | "Atas ao vivo" / copiloto durante a reunião — `sinapse/03-PROJETOS/atas-ao-vivo.md` |

## 3 · O que "muito bom e completo" significa (requisitos)

### R1 · Nunca perder uma reunião
- Gravar **em blocos no disco durante a captura** (WAV ou FLAC segmentado, ou append com header
  corrigido), para que um crash deixe o áudio até o último bloco.
- **Retomar sessão interrompida**: ao abrir, detectar gravação órfã e oferecer
  "processar o que sobrou".
- **Checagem antes de começar**: níveis do mic e do loopback por ~3 s, dispositivo escolhido, e
  aviso claro se um canal está mudo.
- **Indicador visível de que está gravando** (hoje só há um terminal).
- Decidir retenção do áudio: hoje é apagado no fim; com gravação em blocos, apagar **só depois**
  de a transcrição e o backup `.md` estarem confirmados.

### R2 · Transcrição e falantes confiáveis
- **Diarização calibrada**: limiar para voz de loopback + **teto de locutores**; aceitar o nº real
  de participantes quando o Pedro informar.
- **Nomear os falantes**: mapear "Participante 1/2" → nome (informado no início ou deduzido do
  texto e confirmado) — sem isso a ata não atribui tarefa com segurança.
- **Vocabulário do contexto** no `initial_prompt`/hotwords do Whisper (Orbe, Lumen, Vértice,
  SUP-###, nomes do time, termos de produto).
- **Avaliar GPU (CUDA) e modelo maior** (`medium`/`large-v3-turbo`) — medir WER e tempo nas atas
  existentes antes de trocar.

### R3 · Ata estruturada, não só prosa
Saída canônica em **JSON versionado** (a página e o PDF passam a ser renderizações dela):
- contexto, resumo, temas;
- **decisões** (texto, quem decidiu, data, `revisar_em`);
- **encaminhamentos** (o quê, **dono**, **prazo**, origem na transcrição com timestamp);
- **perguntas em aberto** e **riscos**;
- participantes, tipo de reunião, projeto.
Nada de campo inventado: se o prazo não foi dito, fica "não definido" — e isso deve aparecer como
lacuna a fechar, não como dado.

### R4 · Integração com o Claude
- **Resumo com o Claude** como caminho principal ou segunda passada (qualidade muito acima do
  Llama; sem o limite de 40k). Decidir o modo: local via Claude Code lendo a transcrição, ou API.
- Um comando/skill do tipo **`/ata`**: pega a última reunião (ou uma escolhida) e
  1. extrai decisões/encaminhamentos/perguntas;
  2. **propõe** atualizações de memória e de Sinapse;
  3. **propõe** cards/comentários de ClickUp — **nunca publica** sem OK explícito na hora;
  4. mostra o que mudou desde a última reunião do mesmo assunto.
- **Índice pesquisável** das atas (por pessoa, projeto, decisão) para o Claude responder
  "o que ficou decidido com o Mauro sobre X?".

### R5 · Integração com o Sinapse (respeitando as regras do vault)
- O Sinapse recebe **conhecimento e decisão**, não número operacional nem conteúdo de cliente.
- Roteamento **por tipo de reunião** (ver R6): carreira/crescimento → `08-CRESCIMENTO`; projeto
  próprio → nota do projeto; **trabalho da Parresia fica FORA do vault** (vai para o repositório
  de operação, ex.: `qa-parresia/rotinas/decisoes.jsonl`), salvo decisão contrária do Pedro.
- **Log de decisões com `revisar_em`** ("decisão sem revisão vira regra por esquecimento").
- Corrigir o vazamento conhecido: `fala-raio-x.md` lista reuniões **pelo título**, que costuma ter
  nome de cliente.

### R6 · Contexto da reunião na partida
Ao iniciar: **título, tipo** (cliente · Parresia interna · pessoal/estudo), **projeto**,
**participantes esperados**. Isso decide marca, destino dos dados, roteamento para Sinapse/repo e
se sai entregável para cliente.

### R7 · Segurança e privacidade
- Senha (ou token) por reunião; rota de exclusão; prazo de retenção no D1.
- ⚠️ **Decidir onde vive o conteúdo da Parresia.** Hoje toda ata sobe para o Worker/D1/Workers AI
  na conta Cloudflare **pessoal** do Pedro, com marca RYZE. Reunião interna da Parresia
  provavelmente **não deve** sair da máquina, nem levar a marca RYZE.
- Consentimento para gravar continua sendo responsabilidade dele (lembrete no fluxo).

### R8 · Operação sem atrito
- Iniciar em 1 clique (atalho/bandeja), com os campos do R6.
- Falha nunca é silenciosa (Workers AI, upload, vault).
- **Testes**: ao menos fumaça do pipeline com áudio sintético e teste do render; homologação do
  Worker antes de produção.

### R9 · Depois (não bloqueia a v2)
- **Atas ao vivo**: notas em tempo real e conversa com o Claude durante a reunião
  (MVP provável: o gravador escreve a transcrição incremental num arquivo que o Claude lê).
- Domínio próprio (`atas.ryzecode.com.br`, passos no `ARQUITETURA.md`).

## 4 · Ordem sugerida

1. **F0 — Robustez** (R1): nunca mais perder reunião. Pequeno, e é o que mais dói.
2. **F1 — Falantes e qualidade** (R2): diarização calibrada nas 27 atas existentes + nomes + vocabulário; medir GPU.
3. **F2 — Ata estruturada + Claude** (R3, R4, R6): o JSON canônico e o `/ata`.
4. **F3 — Sinapse e roteamento** (R5) e **segurança** (R7).
5. **F4 — Operação e testes** (R8). **F5 — Ao vivo** (R9).

Cada fase termina com: revisão → commit + push (+ deploy do Worker se tocou nele) → registro no
Sinapse (nota `03-PROJETOS/atas.md`).

## 5 · Decisões que o Pedro precisa tomar na primeira sessão

1. Reuniões da **Parresia** sobem para o Worker ou ficam só locais? Com qual marca saem, se saírem?
2. Resumo pelo **Claude** (qual caminho: Claude Code local ou API com chave) ou manter Workers AI?
3. **Guardar o áudio** (e por quanto tempo) ou manter "só texto"?
4. Como informar os participantes: digitando no início, ou o sistema deduz e ele confirma depois?
5. O que da ata de trabalho vai para onde (memória do Claude · repositório de operação · Sinapse)?

## 6 · Regras do Pedro que valem aqui

- Commits **sem** trailer `Co-Authored-By` do Claude.
- **Nada no ClickUp sem OK na hora**; escrita só pelos wrappers com o token dele.
- Operação da Parresia **fora do Sinapse** (a menos que ele diga o contrário); o vault é escrito
  por mim, ele só lê.
- UI: pouca informação, muito respiro; o essencial à vista, o resto recolhido.
- Credencial nunca redigitada nem impressa no transcript.
- "Abrir" = Explorer na pasta com o arquivo selecionado (via PowerShell); `.md` em preview.

## 7 · Onde está o contexto

- `docs/ARQUITETURA.md` — funcionamento atual, armadilhas (§14), receitas (§11).
- Memória do Claude: `atas-reunioes`, `transicao-po-parresia`, `fluxo-trabalho-sinapse`.
- Vault: `03-PROJETOS/atas.md`, `03-PROJETOS/atas-ao-vivo.md`, `08-CRESCIMENTO/fala-raio-x.md`,
  `08-CRESCIMENTO/transicao-para-po.md`.
