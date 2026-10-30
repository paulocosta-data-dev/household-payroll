# Arquitetura inicial

```text
Google Form -> Google Sheets -> pipeline Python -> DuckDB -> HTML estático
                                      ^
                                      |
                         execução manual ou agendada
```

## Responsabilidades

- Google Form: recolha móvel dos registos.
- Google Sheets: respostas originais e interface administrativa.
- Pipeline Python: extração, validação, transformação, cálculos e relatório.
- DuckDB: histórico local persistente nas camadas raw, core e mart.
- HTML: consulta local, sem operações de escrita.
- Docker Compose: execução reproduzível e distribuição familiar.

## Garantias pretendidas

- Ingestão idempotente.
- Um único escritor no DuckDB.
- Bloqueio contra execuções sobrepostas.
- Transações para atualização consistente.
- Relatório substituído apenas após execução bem-sucedida.
- Recuperação de respostas acumuladas enquanto o computador esteve desligado.
- Segredos, dados pessoais e artefactos reais fora do repositório.
