# Atas · problemas e melhorias

Backlog do sistema. Cada item diz o que aconteceu, onde, e o que precisa mudar. A ordem é
de prioridade. Fonte: a primeira reunião longa real da v2 (05/10/2026, 3h09, alinhamento com o
Valter, sessão `2026-10-05_2303_alinhamento-valter`), conferida item a item contra a transcrição.

## Status em 06/10/2026 · tudo no `main` (`21d5bdd` v2.1, `51c602c` v2.2, `6ba25d1` voz)

| # | Item | Estado | Onde |
|---|---|---|---|
| 1 | Editar a ata publicava sozinho | ✅ corrigido + teste que pega o defeito antigo | `atas.py::_reaplicar`, `tests/test_v21.py` |
| 2 | PDF do cliente com a transcrição inteira | ✅ o cliente recebe só os **trechos citados**; a interna segue inteira | `render.html` |
| 3 | Raio-X invisível | ✅ cartão na tela final + `atas.py fala <id>` | `app.py::_cartao_fala`, `atas.py::c_fala` |
| 4 | Ata rasa em reunião longa | ✅ acima de 60 min, estrutura em **blocos de 40 min** + consolidação | `estruturar.py` |
| 5 | Avaliação interna | ✅ etapa `avaliacao` (cliente/Parresia, ≥ 15 min) + passo 4c do /ata | `avaliar.py`, skill |
| 6 | Raio-X mais completo | ✅ ritmo, turnos, maior monólogo, interrupções, resposta, perguntas, cansaço por 30 min, voz (volume e entonação), metas | `analise_fala.py` |
| 7 | Prazo relativo | ✅ "N dias", "N semanas", faixa "4 5 dias", por extenso | `ata._data_coerente` |
| 8 | Lacunas demais | ✅ revisão de decisão não é mais lacuna automática | `ata.lacunas` |
| 9 | Valores, escopo, resumo por tema | ✅ listas auditadas `valores` (V) e `escopo` (S) + `por_tema` | `ata.py`, `render.py` |
| 10 | Trechos "Palavra Por Palavra" do turbo | ✅ 22/10 · causa medida: `condition_on_previous_text` (não as hotwords); Whisper sem condicionar + região picada refeita ou marcada `baixa_confianca` | `transcribe._passada/regioes_picadas`, `ARQUITETURA.md` §5, `tests/test_transcricao_picada.py` |
| 11 | Raio-X grava no Sinapse sem perguntar | ✅ documentado como a única exceção (regra 7 do /ata) | skill |
| 12 | Tema escuro RYZE em tudo (ata, entregável, Raio-X, avaliação) | ✅ v2.2 | `tema.py` |
| 13 | Raio-X com postura, frases para revisar e página por reunião | ✅ v2.2 | `analise_fala.postura`, `raio_x_html.py` |
| 14 | Voz com leitura: o que é, faixas, zona, o que fazer; evolução por bloco de 30 min ("st, volume e tom não significam nada pra mim") | ✅ `6ba25d1` | `analise_fala.leitura_voz`, `raio_x_html._secao_voz`, `tests/test_voz.py` |
| 15 | Raio-X calibrado com fonte: muleta pura × marcador, "tá" verbo fora, confirmação só com "?", "aí" em degraus, "a gente" sem meta, tomou a vez × apoio, fatia por tipo, sílabas/s, paciência, perguntas abertas, compromisso com dono e prazo, limiar de 1.000 palavras, mediana das últimas 5, `fala --recalcular` | ✅ 14/10 | `analise_fala.py` (v3), `ARQUITETURA.md` §17, `tests/test_raio_x_calibrado.py` |
| 16 | Formato da reunião de cliente (descoberta/demo/alinhamento) na janela, opcional e só em cliente; `atas.py formato`; o /ata propõe | ✅ 14/10 | `app.py::inicio`, `atas.py::c_formato`, `tests/test_formato.py` |
| 17 | Recalcular o histórico real do Raio-X com as regras v3 | ✅ 14/10 · 4 reuniões, backup `historico.jsonl.bak-2026-10-14`, vault intocado | `ARQUITETURA.md` §17 |
| 18 | Reunião presencial gravada no celular: `importar`, `vigiar`, "Você" pela amostra de voz e a confirmar, tipo pendente | ✅ 14/10 · ⏳ falta calibrar em áudio de celular real | `celular.py`, `ARQUITETURA.md` §18, `tests/test_celular.py` |
| 19 | Modo treino: ensaio sozinho (reunião ou explicar tema), só o microfone, Raio-X de monólogo (ritmo, pausas, muletas, entonação) contra o alvo, o último treino e as reuniões, retorno do Claude auditado; fora do Raio-X das reuniões e do vault | ✅ 14/10 · ✅ 22/10 "Ler em voz alta" (texto com barras, pausa nas barras) e ritmo ao vivo (small na GPU, ±0,18 sílaba/s do turbo) · ⏳ falta o primeiro treino real | `treino.py`, `app.py::treino_*`, `ARQUITETURA.md` §19, `tests/test_treino.py` |
| 20 | Marcar momento (ideia do Granola): Ctrl+Alt+M global ou botão durante a gravação → `marcas` no sessao.json; o Claude prioriza o trecho (45 s antes, 15 s depois); seção "Momentos marcados" auditada no topo da ata interna, fora do entregável; `marcar`/`marcas` no CLI, `importar --marcas`; desde 22/10, `[mm:ss] ★ MARCA` no `ao-vivo.md` no ponto certo | ✅ 14/10 · ✅ 22/10 marca no ao vivo · ⏳ falta a primeira reunião real marcada ao vivo | `marcas.py`, `atalho.py`, `app.py::_ligar_atalho`, `ARQUITETURA.md` §20, `tests/test_marcas.py` |
| 21 | Daily da Parresia: `formato daily` (formato por tipo), fora de toda medição com trava no ponto de escrita; ata `atas/daily@1` (com você, frentes rastreadas, por pessoa, card conferido a ±60 s, menção não tratada); quem falou sem digitar nomes (teto próprio + rodada); "Gravar a próxima daily"; `atas.py daily` | ✅ 19/10 · ⏳ não calibrado: falta a primeira daily de 1 h gravada de verdade | `daily.py`, `sessao.fora_da_medicao`, `ARQUITETURA.md` §21, `tests/test_daily.py` |
| 22 | Ao vivo intervencionista: liga reunião a reunião (Mais opções, só com GPU; liga o ao vivo junto; liga/desliga no meio); filtro sem IA (pergunta para ele, card/frente, valor/prazo, projeto; daily só os dois primeiros); Claude só leitura, 2 linhas com fonte ou "não sei"; teto 20 e 45 s, uma por vez; cartão sem foco no canto; `intervencoes.jsonl` | ✅ 22/10 · ⏳ falta a primeira reunião real com ele ligado | `intervencionista.py`, `app.py::_ligar_interv`, `ARQUITETURA.md` §22, `tests/test_intervencionista.py` |
| — | Worker v2 no ar | ✅ 22/10/2026 17:10 UTC (`e80b6b7d…`, ryzecode08) · **vazio**: o Pedro decidiu não publicar ("não vejo motivo para esse de publicar atas") e tirou tudo do ar (26 da v1 despublicadas + 2 órfãs apagadas; backup do D1 em `atas-salvas/_backup-d1-atas-2026-10-22.sql`). As 3 atas `pendente` ficam locais; `legado-proteger` sem alvo | `worker/`, `ARQUITETURA.md` §14 |
| — | Marcar trechos fora de pauta | ⏳ parcial: o prompt tira de resumo e itens; falta marcar na transcrição interna | — |

Medido na reunião de 05/10 com a v2.1: ritmo **193 pal/min** (meta 130–180), muletas
**36,9 → 53,5 por mil** do primeiro ao último bloco (cansaço), entonação **3,2 semitons**.

## 🔴 Problemas (corrigir antes do próximo uso com cliente)

### 1. Editar a ata publicava a página do cliente sozinho · ✅ **corrigido e com teste (v2.1)**
`atas.py render`, `falantes` e `confirmar` chamavam `pipeline.reaplicar(publicar_=not sem_publicar)`,
ou seja, `True`, que é **pedido explícito** de publicação. Em 06/10 o `render` tentou publicar a
ata do Valter; só não saiu porque o Worker v2 não está no ar (HTTP 404). Corrigido em
`local/atas.py::_reaplicar` para `False if sem_publicar else None` (só atualiza a página se ela
**já** estiver no ar), igual ao `processar`. O teste de regressão está em `tests/test_v21.py`.

### 2. O entregável do cliente leva a transcrição inteira
`render.html(cliente=True)` inclui a transcrição completa (`<details class="transc">`). A ata de
05/10 virou um PDF de **179 páginas** com 15 minutos de conversa pessoal fora de pauta.
Um clique em "Publicar" mandaria isso ao cliente.
**Mudar:** por padrão, o entregável do cliente **não** leva transcrição; ou leva só os trechos
citados pelos itens verificados. Transcrição completa só na ata interna, ou por opção explícita.
Junto: marcar trechos **fora de pauta** (pessoal, político) para nunca saírem da máquina.

### 3. O Raio-X da Fala calcula, mas ninguém vê
`analise_fala.py` roda (etapa `raio_x`) e grava `fala-analise/` e a nota
`08-CRESCIMENTO/fala-raio-x.md`, mas a v2 **não mostra nem abre nada**. A v1 abria o painel
`raio-x.html` sozinha no fim (`run.py::abrir`). O Pedro achou que a função tinha sumido.
**Mudar:** no fim do processamento, a janela mostra um cartão com os números da reunião
(fatia de fala, confirmações/min, muletas/1k, tendência) e um botão "Ver Raio-X"; e um comando
`atas.py fala <id|ultima>` que imprime o relatório e abre o painel.

### 4. A estrutura automática fica rasa em reunião longa
190 min de reunião foram estruturados em 86 s, numa passada só. Ficaram de fora: os R$ 550 da
primeira parcela, a lista de funcionalidades do IoT, as regras do pacote de conteúdo (mês
corrido, artigo interno × de convidado, manual só PDF) e os pontos do Instituto. Tudo isso
estava na transcrição e foi acrescentado à mão.
**Mudar:** acima de ~60 min, estruturar **por blocos** (30–40 min, com sobreposição) e
consolidar; ou uma segunda passada só para "o que ficou de fora" com a lista do que a primeira já
pegou.

## 🟡 Melhorias pedidas

### 5. Avaliação interna junto da ata (pedido do Pedro, 06/10)
Toda reunião de negociação ou cliente deve sair com uma **parte interna**, nunca no entregável:
- **Afirmações conferidas:** o que o Pedro afirmou que estava certo, errado ou exagerado, com o
  timestamp e o que é verdade (cruzando com código, memória e números medidos).
- **Valores e negociação:** se os preços fecham contra o piso de hora dele, as concessões feitas e
  com ou sem contrapartida, a ancoragem, o que ficou mal precificado.
- **Postura:** o que funcionou e o que trabalhar, com os números do Raio-X.
- **O que corrigir com o cliente:** promessas erradas que ele vai testar.

Modelo pronto: `atas-salvas/2026-10-05_2303_alinhamento-valter/avaliacao-interna.md`.
Como a conferência exige cruzar com código e memória, ela é trabalho do **/ata** (Claude Code com
acesso aos repositórios), não do `estruturar.py`. O /ata deve oferecer a avaliação sempre que o
tipo for `cliente` ou `parresia`.

### 6. Raio-X da fala mais completo ("análise da minha voz")
Hoje conta palavras (muletas, confirmações, bordões, fatia). Dá para medir também, com o que já
temos (timestamps por palavra e o áudio do microfone guardado 30 dias):
- **ritmo** (palavras por minuto) e a variação dele ao longo da reunião;
- **pausas** e silêncios longos; **turno médio** e o **maior monólogo**;
- **interrupções**: fala do Pedro começando com o outro ainda falando (sobreposição mic × loop);
- **cansaço**: muletas e confirmações por bloco de 30 min (a reunião de 05/10 foi das 23h às 2h);
- **voz** (do áudio): volume e variação de entonação, para "falo monótono?" e "falo baixo?";
- comparação com as **metas** da nota `fala-e-apresentacao` (ex.: "aí" e "a gente").

### 7. Prazo relativo na auditoria
"Limite máximo de 15 dias", "em 4 ou 5 dias" e "semana que vem" viram lacuna mesmo ditos, porque
`ata._data_coerente` só entende "dia N", dia da semana e "N/M". **Mudar:** aceitar "N dias" e
"N semanas" contados da reunião, com tolerância de ±1 dia.

### 8. Lacunas demais
A ata de 05/10 tem 26 lacunas, 15 delas "data de revisão" de decisão. Vira ruído e esconde a
lacuna que importa (prazo de pagamento, por exemplo). **Mudar:** `revisar_em` vazio não vira
lacuna por padrão; só o prazo de encaminhamento com dono.

### 9. Campos que faltam no esquema da ata
- **Valores e pagamentos** (quanto, quando, condição: "R$ 450 na publicação na Play Store").
  Hoje ficam escondidos dentro do texto de uma decisão.
- **Itens de escopo / requisitos** (a lista de funcionalidades do IoT não tinha onde entrar).
- **Resumo por tema**: a reunião tratou de 3 projetos (conteúdo, Instituto, IoT) e a ata tem um
  só `projeto` (vazio). O resumo para o cliente que o Pedro prometeu é **por tema**.

### 10. Transcrição do áudio da chamada com trechos "Palavra Por Palavra"
Entre 1:47:28 e 1:57:00 (o Valter compartilhando tela e mexendo em loja) o turbo devolveu falas
com cada palavra em maiúscula e quebrada ("Ele Ter Um Site Já Que Descreve…"). Investigar se é o
vocabulário (hotwords) num trecho de áudio ruim, e marcar trecho de baixa confiança.
**✅ 22/10/2026 — medido numa cópia da sessão (a original conferida por hash, intacta).** A hipótese das
hotwords **não** se confirmou; a causa é o `condition_on_previous_text` do Whisper.
- O defeito não era só de 1:47 a 1:57: no canal da chamada, a fração de palavras em maiúscula fora do começo de
  frase sobe a partir de ~0:38 e fica em 33–49% até o fim (3h09), com o pior em 1:45–1:55 (71–89%, 1 palavra por
  trecho). O canal do microfone, na mesma reunião, ficou normal.
- O trecho 1:46:20–1:58:00 transcrito **sozinho**, com e sem hotwords, com e sem condicionar: 0–11% em todos os
  4 casos, e mais palavras que a produção (1.460–1.782 × 1.252). Sozinho, ele não reproduz.
- Do 0:35 ao 1:58 com as configurações de produção: 3%. O arquivo **inteiro** com as configurações de produção:
  o modo voltou, mas noutro ponto (2:15 até o fim, 31–43%). Sem condicionar, mesmas hotwords: 2–14% em todas as
  janelas, 14,7 mil palavras (produção 14,5 mil) e 399 s × 1.002 s de GPU.
- Conclusão: o modo começa num ponto aleatório e o texto anterior, usado como prompt, o carrega até o fim.
**Feito:** `whisper_condicionar: false` por padrão (config) e rede de segurança `regioes_picadas` (fala > 70% em
maiúscula ou janela de 5 min > 30%) → refaz a região sozinha sem hotwords e fica a melhor; se continuar picada,
`baixa_confianca` no trecho e aviso na sessão; o detalhe da etapa de transcrição diz quantos trechos foram
refeitos. Nas transcrições de outubro o detector achou 05/10, 19/10 (2,6 min no fim de 4h47) e 09/10 (0,3 min de
"Alô, Alô…"). **Não feito:** retranscrever as reuniões antigas (só com o Pedro pedindo; a de 05/10 tem áudio até
04/11: `processar <id> --forcar transcricao,estrutura` refaz a ata inteira).

### 11. A etapa `raio_x` grava no Sinapse sem perguntar
É de propósito (nota auto, sem título), mas contradiz a regra do /ata "nada no Sinapse sem OK".
Deixar escrito na skill que a nota `fala-raio-x.md` é a **única** exceção.

## Já anotados em outros lugares
- ~~Worker v2 não deployado~~ → no ar desde 22/10/2026 e vazio; publicação não é usada (decisão do Pedro): `ARQUITETURA.md` §14.
- Ao vivo nunca testado em reunião real: `ARQUITETURA.md` §13.

## 15. Raio-X calibrado (14/10/2026) · ✅
Pesquisa de referências (ritmo de João Pessoa, Gong, Abralin, CoDAS) mostrou que parte das metas
media a régua errada: em 13/10 as "muletas" eram 77,2/1k, mas boa parte era "tá" verbo e marcador;
"a gente" é pronome padrão; o "aí" ≤8 era inalcançável; reunião de 600 palavras era julgada igual a
uma de 13 mil. Regras, fontes e limites em `ARQUITETURA.md` §17. Recalcular o histórico real:
`atas.py fala --recalcular` (não escreve no vault) — **rodado em 14/10** (item 17).
~~Pendente: a janela não pergunta o `formato`~~ → ✅ item 16.

## 16–18. Formato, recálculo e celular (14/10/2026) · ✅
- **Formato** na tela de partida, só em cliente, "não sei" de padrão; `atas.py formato` corrige.
- **Recálculo** do histórico real: 4 reuniões. Base da próxima: muleta pura 31,4/1k, "aí" 17,9/1k,
  confirmação 1,56/min, fatia 49%, 200 ppm, 5,92 sílabas/s, compromisso com dono e prazo 56%.
- **Celular**: `atas.py importar <arquivo>` / `vigiar <pasta>`. Passo a passo no README; como acha o
  Pedro, números medidos e limites em `ARQUITETURA.md` §18.
  **Pendente:** calibrar os limiares (0,45 / margem 0,10) com a primeira reunião presencial real;
  testar o gravador do celular 10 min com a tela apagada antes dela.

## 19. Modo treino (14/10/2026) · ✅
Pedido do Pedro ("gosto do modo treino para reunião"). Janela: link "Treinar" → 3 telas. CLI:
`treinar`, `treino <áudio>`, `treinos [--manter <id>]`. O que mede, réguas, isolamento e limites em
`ARQUITETURA.md` §19. Conferido em 14/10 com voz sintética pt-BR (7 de 7 pausas achadas) e o
`claude -p` real (US$ 0,07 e ~21 s por treino curto).
**Pendente:**
- **Primeiro treino real** com o fone: conferir se a faixa de pausas (8 a 15/min, heurística) e o
  limiar de 0,5 s fazem sentido na voz dele (o Whisper encurta a pausa em ~0,2 s).
- ~~Ritmo ao vivo~~ ✅ 22/10: `ao_vivo.RitmoAoVivo`, `small` na GPU com o tempo de cada palavra, últimos 20 s a
  cada 5 s. Medido contra o turbo em 30 janelas da voz real do Pedro: diferença média 0,18 sílaba/s (p90 0,45),
  2,3 s de GPU por estimativa. Só com GPU. `ARQUITETURA.md` §19.
- ~~Texto pronto para a leitura ritmada~~ ✅ 22/10: tipo "Ler em voz alta", texto da nota de `02-ESTUDO` ou de 3
  embutidos, barras a cada 5–8 palavras e a medida "pausa nas barras" no lugar das muletas.
- Ainda pendente dos exercícios guiados: o **roteiro de 3 tópicos a 5,0** (hoje só o alvo à mão em "Mais opções").
- Calibrar com os primeiros treinos reais: limiar de 0,3 s e meta de 70% da pausa nas barras.

## 21. Daily da Parresia (19/10/2026) · ✅ · ⏳ não calibrado
Pedido do Pedro: dailies de >1 h com 7+ pessoas, rodada pelo nome, ele fala pouco (09/10: 8,9%); quer achar
quem disse o quê sobre qual card (o SUP-953 do Rogério se perdeu numa daily não gravada) sem digitar nomes, e
tem duas dailies seguidas. Feito: `formato daily` (formato por tipo), fora de toda medição com trava no ponto
de escrita (`sessao.fora_da_medicao`), ata `atas/daily@1`, teto próprio da diarização + rodada como pista,
"Gravar a próxima daily", `atas.py daily`, `formato <id> daily` para reunião já medida, `/ata` com roteiro
curto (passo 1e). Detalhe, números e limites em `ARQUITETURA.md` §21.
**Pendente:**
- **Calibrar** na primeira daily de 1 h gravada de verdade, sabendo quantas pessoas falaram: `calibrar <id>
  --daily` (teto 1,5% / 15 s / 12 vozes), a janela da rodada (10 s) e a do card (±60 s) são palpite.
- **Completar `daily_equipe`** no `config.json` (lista inicial de 11 nomes, com apelidos usados: "Lena"…).
- ~~Decidir a 09/10~~ ✅ 19/10: o Pedro confirmou que era um trecho da daily; `formato daily` aplicado (linha
  fora do Raio-X, backup `historico.jsonl.bak-2026-10-19`, avaliação guardada como `*.antes-daily.*`). A ata
  ainda é a de reunião normal: `processar <id> --forcar transcricao,estrutura` refaz no formato daily.
- A rodada não foi medida numa rodada de verdade (a 09/10 é a apresentação do método: 2 pistas, 1 em
  conflito com o nome deduzido pelo texto).
- A diarização da daily roda na CPU: ~835 s para 46 min de áudio (09/10), ou seja ~18 min a mais numa daily de
  1 h antes da ata sair.

## 22. Ao vivo intervencionista (pedido de 21/10, feito em 22/10/2026) · ✅ · ⏳ não calibrado (não usado numa reunião real)
Feedback do Pedro depois de usar o ao vivo numa reunião, com o Claude lendo `ao-vivo.md` pelo chat: "muito muito
bom". O pedido: um modo que fica ouvindo o tempo todo e traz a resposta **sem ele pedir**. Decidido em 21/10: o
Pedro liga reunião a reunião, desligado por padrão, em qualquer tipo.
Feito: "Intervencionista" em "Mais opções" (só com GPU; liga o ao vivo junto) e uma linha discreta na gravação que
liga/desliga no meio; filtro determinístico (pergunta dirigida a ele sem contar "você entendeu?", card/frente,
valor/prazo, afirmação sobre projeto do Sinapse; na daily só os dois primeiros); `claude -p` só leitura (memória,
Sinapse, repos, atas) com resposta de até 2 linhas e fonte, ou "não sei" (só no registro); teto `max_chamadas` 20,
`intervalo_min_s` 45, uma chamada por vez; cartão sem foco no canto inferior direito que some em 25 s;
`intervencoes.jsonl` na pasta da sessão, que o `/ata` lê. Medidas, regras e limites em `ARQUITETURA.md` §22.
**Pendente:**
- **Primeira reunião real** com ele ligado: ler o `intervencoes.jsonl` com o Pedro e calibrar o que foi útil.
- **Teto**: no ao vivo de 19/10 (4h47 com o Valter) o filtro acharia 127 gatilhos e o teto de 20 acabaria em
  ~1h58. Decidir com o uso se sobe o teto, aperta o filtro ou reserva chamadas para pergunta.
- Atraso medido de ~40–60 s da fala ao cartão (janela do ao vivo + 7–10 s do Claude).
