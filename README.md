# Sistema de Controle de Gastos Mensais (Python + MySQL)

Fundação com arquitetura limpa, tipos estritos e regras de domínio desacopladas de qualquer interface de chat (Telegram, WhatsApp ou CLI).

---

## 🏗️ Estrutura do Projeto

```text
bot-telegram-poti-app/
├── sql/
│   ├── schema.sql            # Definição DDL de tabelas, índices e constraints (InnoDB, utf8mb4)
│   └── seed.sql              # Dados iniciais de tópicos e configurações padrão
├── src/
│   ├── config.py             # Carregamento seguro de variáveis de ambiente com python-dotenv
│   ├── db.py                 # Conexão PyMySQL, gerenciamento de transações e DictCursor
│   ├── exceptions.py         # Exceções de domínio (CategoryNotFoundError, InvalidAmountError, etc.)
│   ├── services/
│   │   └── budget_service.py # Todas as regras de negócio de orçamento e transações
│   └── utils/
│       └── money.py          # Conversão segura para Decimal(10,2), BRL e slugs sem acentos
├── scripts/
│   └── smoke_test.py         # Script CLI para testar todas as operações no banco e validações
├── tests/
│   └── test_budget_service.py # Testes unitários com unittest e mocks
├── .env.example              # Modelo de variáveis de ambiente
├── requirements.txt          # Dependências do projeto
└── README.md                 # Documentação técnica da fundação
```

---

## 📊 Modelagem do Banco de Dados (MySQL)

Todos os campos monetários utilizam o tipo `DECIMAL(10, 2)` para evitar quaisquer imprecisões de ponto flutuante binário.

1. **`app_settings`**: Armazena parâmetros globais padrão (`default_salary = 1800.00`, `default_spending_limit`).
2. **`categories`**: Tópicos de despesas com suporte a *soft delete* (`is_active = 0`), preservando integridade referencial com lançamentos anteriores.
3. **`monthly_plans`**: Planejamento financeiro mensal isolado por `month_ref` (`CHAR(7)`, ex: `'2026-11'`). Permite alterar o salário ou teto de um mês sem afetar meses passados.
4. **`transactions`**: Registro individual de cada despesa vinculada a uma categoria (`category_id`) e a um mês de referência (`month_ref`).

---

## 🚀 Como Configurar e Executar

### 1. Criar e Ativar Ambiente Virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configurar Variáveis de Ambiente

Copie o `.env.example` para `.env` e configure suas credenciais do MySQL:

```bash
cp .env.example .env
```

Exemplo de configuração:
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=sua_senha_mysql
DB_NAME=expense_control
DB_CHARSET=utf8mb4
```

### 3. Inicializar o Banco e Executar o Smoke Test

Você pode aplicar o `schema.sql` e o `seed.sql` diretamente no MySQL ou executar via script CLI:

```powershell
# Aplica schema/seed e roda o ciclo completo de testes no banco
python scripts/smoke_test.py --init-db

# Ou rode em modo offline (valida tipos, slugs e formatações sem conectar ao banco)
python scripts/smoke_test.py --skip-db
```

### 4. Executar os Testes Unitários

```powershell
python -m unittest discover tests
```

---

## 💼 Exemplos de Uso do `BudgetService`

```python
from decimal import Decimal
from src.services.budget_service import BudgetService

service = BudgetService()

# 1. Obter ou criar plano do mês (ex: 2026-11)
plan = service.get_or_create_month_plan("2026-11")

# 2. Registrar um gasto
resultado = service.add_expense(
    category_slug="faculdade",
    amount="284,71",
    description="Mensalidade Nov",
    month_ref="2026-11"
)

# Retorno estruturado pronto para formatar no Telegram:
# - resultado['amount'] -> Decimal('284.71')
# - resultado['category']['total_spent'] -> Decimal('284.71')
# - resultado['monthly_plan']['remaining_salary'] -> Saldo restante do salário
# - resultado['warning_80'] -> True se atingiu >= 80% do teto
# - resultado['warning_100'] -> True se atingiu >= 100% do teto

# 3. Adicionar/editar novo tópico (ex: Prestação Carro)
service.upsert_category("Prestação Carro", planned_amount="600.00", monthly_limit="600.00")

# 4. Obter resumo consolidado do mês
resumo = service.get_monthly_summary("2026-11")
```
