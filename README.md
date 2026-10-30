# Household Payroll

Aplicação local para registar, reconciliar, aprovar e apurar trabalho de serviço doméstico em Portugal.

O projeto usa Google Forms e Google Sheets para recolha e administração, Python para validação e cálculos, DuckDB para armazenamento local e HTML estático para consulta. A execução será distribuída através de Docker Compose e de um instalador assistido para Windows.

## Estado

O projeto está na primeira fase de implementação. Nesta etapa existe apenas a fundação executável e a documentação das decisões. Ainda não existem integrações com Google, cálculos financeiros definitivos ou dados pessoais.

## Princípios

- Dados pessoais, credenciais, bases de dados e relatórios reais nunca entram no Git.
- Respostas originais são preservadas; correções e anulações são novos eventos.
- Apenas valores explicitamente aprovados entram num apuramento.
- Períodos fechados são imutáveis; alterações posteriores originam acertos.
- Regras financeiras e tarifas são versionadas por data de vigência.
- Cálculos legais não confirmados são apresentados como estimativas, nunca como valores definitivos.

## Execução da fundação

Com Python 3.12 ou superior:

```powershell
$env:PYTHONPATH = "src"
python -m household_payroll healthcheck
```

Com Docker:

```powershell
docker compose run --rm pipeline healthcheck
```

## Estrutura

```text
config/       configuração pública e exemplos
docs/         arquitetura e decisões
installer/    futuro instalador Windows
src/          código da aplicação
tests/        testes automatizados
```

Consulte [docs/decisions.md](docs/decisions.md) para as decisões funcionais já aprovadas.
