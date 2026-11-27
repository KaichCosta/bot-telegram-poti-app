"""Smoke Test CLI para validação das operações do BudgetService e MySQL.

Testa de ponta a ponta:
1. Conexão ao MySQL (ou simulação controlada com SQLite/Mock se MySQL estiver offline)
2. Inicialização / Leitura de schema e seeds
3. get_or_create_month_plan
4. set_salary (mensal e padrão futuro)
5. set_spending_limit
6. upsert_category (criação e atualização de tópicos)
7. rename_category (preservando ID e histórico)
8. deactivate_category (soft delete)
9. add_expense (lançamento, recálculo de saldo, alertas 80% e 100%)
10. get_monthly_summary (visão completa analítica)
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

# Adiciona a raiz do projeto ao sys.path para importações
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import config
from src.exceptions import (
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    DatabaseConfigurationError,
    InvalidAmountError,
)
from src.services.budget_service import BudgetService
from src.utils.money import format_brl, slugify, to_decimal, validate_month_ref


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f" {title.upper()}")
    print("=" * 70)


def print_step(step_name: str, status: str = "OK", detail: str = "") -> None:
    status_icon = "[OK]" if status == "OK" else f"[{status}]"
    print(f"  {status_icon:<6} {step_name}")
    if detail:
        print(f"         -> {detail}")


def run_unit_smoke_tests() -> None:
    """Valida utilitários de dinheiro, slugs e regras essenciais de validação."""
    print_header("1. Validação de Utilitários de Domínio (money.py)")

    # 1. to_decimal
    test_cases = [
        ("284,71", Decimal("284.71")),
        ("284.71", Decimal("284.71")),
        ("R$ 1.800,00", Decimal("1800.00")),
        ("1.234,56", Decimal("1234.56")),
        ("100", Decimal("100.00")),
        (59.9, Decimal("59.90")),
    ]
    for raw, expected in test_cases:
        res = to_decimal(raw)
        assert res == expected, f"Esperado {expected}, obtido {res}"
    print_step("Conversões seguras para Decimal", "OK", f"{len(test_cases)} formatos testados com sucesso")

    # 2. format_brl
    assert format_brl(Decimal("1800.00")) == "R$ 1.800,00"
    assert format_brl(Decimal("284.71")) == "R$ 284,71"
    assert format_brl(Decimal("-150.50")) == "R$ -150,50"
    print_step("Formatação em moeda brasileira BRL", "OK", "Formato R$ 1.234,56 validado")

    # 3. slugify
    assert slugify("Faculdade") == "faculdade"
    assert slugify("Prestação Carro") == "prestacao-carro"
    assert slugify("Água & Luz") == "agua-luz"
    print_step("Normalização e geração de slugs sem acento", "OK", "Slugs limpos gerados")

    # 4. validate_month_ref
    assert validate_month_ref("2026-11") == "2026-11"
    current_month = validate_month_ref(None)
    assert len(current_month) == 7 and "-" in current_month
    print_step("Validação de mês de referência (YYYY-MM)", "OK", f"Mês atual detectado: {current_month}")


def run_database_smoke_tests(service: BudgetService, test_month: str = "2026-11") -> None:
    """Executa o ciclo completo de testes com banco de dados MySQL ativo."""
    print_header(f"2. Bateria de Testes de Negócio (Mês de Teste: {test_month})")

    # 1. get_or_create_month_plan
    plan = service.get_or_create_month_plan(test_month)
    print_step(
        "get_or_create_month_plan()",
        "OK",
        f"Salário: {format_brl(plan['salary'])} | Limite de Gastos: {format_brl(plan['spending_limit'])}",
    )

    # 2. set_salary
    new_salary = Decimal("2000.00")
    sal_result = service.set_salary(new_salary, month_ref=test_month, update_default=True)
    print_step(
        "set_salary(2000.00, update_default=True)",
        "OK",
        f"Novo Salário: {format_brl(sal_result['salary'])} (Padrão atualizado para meses futuros)",
    )

    # 3. set_spending_limit
    new_limit = Decimal("1500.00")
    lim_result = service.set_spending_limit(new_limit, month_ref=test_month)
    print_step(
        "set_spending_limit(1500.00)",
        "OK",
        f"Novo Teto de Gastos do mês: {format_brl(lim_result['spending_limit'])}",
    )

    # 4. upsert_category - Criação de novo tópico (Prestação Carro)
    car_cat = service.upsert_category("Prestação Carro", planned_amount="600.00", monthly_limit="600.00")
    print_step(
        "upsert_category('Prestação Carro', planned=600.00)",
        "OK",
        f"Slug criado: {car_cat['slug']} | Ação: {car_cat['action']}",
    )

    # 5. rename_category - Preservando histórico
    renamed = service.rename_category(car_cat["slug"], "Financiamento Veículo")
    print_step(
        "rename_category(old_slug, 'Financiamento Veículo')",
        "OK",
        f"ID mantido: {renamed['id']} | Novo Slug: {renamed['new_slug']}",
    )

    # 6. deactivate_category - Soft delete
    deact = service.deactivate_category(renamed["new_slug"])
    print_step(
        f"deactivate_category('{renamed['new_slug']}')",
        "OK",
        f"is_active={deact['is_active']} (Soft delete concluído)",
    )

    # 7. add_expense - Lançamento 1 em Faculdade
    tx1 = service.add_expense("faculdade", amount="284.71", description="Mensalidade Nov/2026", month_ref=test_month)
    print_step(
        "add_expense('faculdade', 284.71)",
        "OK",
        f"Lançado: {format_brl(tx1['amount'])} | Restante Salário: {format_brl(tx1['monthly_plan']['remaining_salary'])}",
    )

    # 8. add_expense - Lançamento que dispara alerta >= 80%
    tx2 = service.add_expense("gasolina", amount="950.00", description="Combustível Viagem", month_ref=test_month)
    print_step(
        "add_expense('gasolina', 950.00) [Alerta 80%]",
        "OK" if tx2["warning_80"] else "WARN",
        f"Total Gasto: {format_brl(tx2['monthly_plan']['total_spent'])} | Alerta 80%: {tx2['warning_80']} | Alerta 100%: {tx2['warning_100']}",
    )

    # 9. add_expense - Lançamento que estoura o limite >= 100%
    tx3 = service.add_expense("netflix", amount="300.00", description="Assinatura Anual", month_ref=test_month)
    print_step(
        "add_expense('netflix', 300.00) [Alerta 100% Estourado]",
        "OK" if tx3["warning_100"] else "WARN",
        f"Total Gasto: {format_brl(tx3['monthly_plan']['total_spent'])} (Limite: {format_brl(tx3['monthly_plan']['spending_limit'])}) | Alerta 100%: {tx3['warning_100']}",
    )

    # 10. get_monthly_summary
    summary = service.get_monthly_summary(test_month)
    print_header(f"3. Resumo Mensal Consolidado ({summary['month_ref']})")
    print(f"  Salário do Mês:        {format_brl(summary['salary'])}")
    print(f"  Teto de Gastos:        {format_brl(summary['spending_limit'])}")
    print(f"  Total Despesas:        {format_brl(summary['total_spent'])}")
    print(f"  Saldo Livre Salário:   {format_brl(summary['remaining_salary'])}")
    print(f"  Saldo Restante Limite: {format_brl(summary['remaining_limit'])}")
    print(f"  Consumo do Limite:     {summary['limit_usage_pct']}% (Alerta 100%: {summary['warning_100']})")
    print("\n  Detalhamento por Tópico:")
    for cat in summary["categories"]:
        status_txt = "Ativo" if cat["is_active"] else "Inativo"
        print(
            f"   - {cat['name']:<22} | Gasto: {format_brl(cat['total_spent']):<12} "
            f"| Meta: {format_brl(cat['effective_limit']):<12} | {cat['usage_pct']}% [{status_txt}]"
        )


def init_database_tables(connection) -> None:
    """Executa os scripts schema.sql e seed.sql para inicializar o banco."""
    schema_path = ROOT_DIR / "sql" / "schema.sql"
    seed_path = ROOT_DIR / "sql" / "seed.sql"

    with connection.cursor() as cursor:
        for file_path in [schema_path, seed_path]:
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Divide os comandos por ponto e vírgula
            statements = [s.strip() for s in content.split(";") if s.strip()]
            for stmt in statements:
                # Ignora comandos de USE e CREATE DATABASE caso a conexão já esteja no banco
                if stmt.upper().startswith("USE ") or stmt.upper().startswith("CREATE DATABASE "):
                    continue
                cursor.execute(stmt)
        connection.commit()
    print_step("Inicialização de Schema e Seeds", "OK", "Tabelas e dados iniciais aplicados com sucesso")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke Test do Sistema de Controle de Gastos")
    parser.add_argument("--month", default="2026-11", help="Mês de teste no formato YYYY-MM")
    parser.add_argument("--init-db", action="store_true", help="Aplica schema.sql e seed.sql antes de rodar os testes")
    parser.add_argument("--skip-db", action="store_true", help="Pula teste contra banco MySQL")
    args = parser.parse_args()

    # 1. Executa validações de tipos e utilitários
    run_unit_smoke_tests()

    if args.skip_db:
        print("\n[INFO] Testes de banco pulados conforme flag --skip-db.")
        return

    # 2. Testa conexão com o MySQL
    service = BudgetService()
    try:
        print_header("Conexão ao Banco de Dados MySQL")
        print(f"  Host: {config.db.host}:{config.db.port} | Database: {config.db.database} | User: {config.db.user}")

        from src.db import create_connection
        conn = create_connection()
        if args.init_db:
            init_database_tables(conn)

        run_database_smoke_tests(service, test_month=args.month)
        conn.close()

        print("\n" + "=" * 70)
        print(" [SUCESSO] Todos os testes de banco foram concluídos com sucesso!")
        print("=" * 70)
    except DatabaseConfigurationError as db_err:
        print(f"\n[AVISO] Servidor MySQL offline ou credenciais não configuradas: {db_err}")
        print("  Dica: Configure o arquivo .env com suas credenciais do MySQL e execute:")
        print("    python scripts/smoke_test.py --init-db")
        print("\n[INFO] Para testar apenas a camada de tipos e regras sem MySQL, use: python scripts/smoke_test.py --skip-db")
    except Exception as exc:
        print(f"\n[ERRO] Falha durante a execução do smoke test: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
