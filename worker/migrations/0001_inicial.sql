-- Tabela da v1 (jul/2026). Idempotente: no banco de produção, que já a tem, não faz nada.
CREATE TABLE IF NOT EXISTS reunioes (
  id       TEXT PRIMARY KEY,
  titulo   TEXT NOT NULL,
  data     TEXT NOT NULL,
  segments TEXT NOT NULL,
  resumo   TEXT
);
