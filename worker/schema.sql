-- Gerado de migrations/ (0001 + 0002). Para aplicar num banco existente use as migrações:
--   npx wrangler d1 migrations apply atas --remote
CREATE TABLE IF NOT EXISTS reunioes (
  id       TEXT PRIMARY KEY,
  titulo   TEXT NOT NULL,
  data     TEXT NOT NULL,
  segments TEXT NOT NULL,
  resumo   TEXT
);
ALTER TABLE reunioes ADD COLUMN chave TEXT;        -- id da sessão local: republicar atualiza
ALTER TABLE reunioes ADD COLUMN html TEXT;         -- entregável renderizado na máquina (NULL = ata da v1)
ALTER TABLE reunioes ADD COLUMN senha_hash TEXT;   -- sha256(sal:senha)
ALTER TABLE reunioes ADD COLUMN senha_sal TEXT;
ALTER TABLE reunioes ADD COLUMN expira_em TEXT;    -- ISO; o cron diário apaga o que passou
CREATE UNIQUE INDEX IF NOT EXISTS idx_reunioes_chave ON reunioes(chave);
