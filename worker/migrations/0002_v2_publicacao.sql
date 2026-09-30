-- v2 (30/09/2026): o Worker passa a guardar o HTML pronto, com senha e expiração.
ALTER TABLE reunioes ADD COLUMN chave TEXT;        -- id da sessão local: republicar atualiza
ALTER TABLE reunioes ADD COLUMN html TEXT;         -- entregável renderizado na máquina (NULL = ata da v1)
ALTER TABLE reunioes ADD COLUMN senha_hash TEXT;   -- sha256(sal:senha)
ALTER TABLE reunioes ADD COLUMN senha_sal TEXT;
ALTER TABLE reunioes ADD COLUMN expira_em TEXT;    -- ISO; o cron diário apaga o que passou
CREATE UNIQUE INDEX IF NOT EXISTS idx_reunioes_chave ON reunioes(chave);
