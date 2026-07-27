CREATE TABLE IF NOT EXISTS reunioes (
  id       TEXT PRIMARY KEY,   -- slug aleatório não-adivinhável (vai na URL /r/<id>)
  titulo   TEXT NOT NULL,
  data     TEXT NOT NULL,      -- timestamp ISO
  segments TEXT NOT NULL,      -- JSON: [{speaker,start,end,text}]
  resumo   TEXT               -- JSON: {resumo_executivo,decisoes[],proximos_passos[]}  (pode ser NULL)
);
