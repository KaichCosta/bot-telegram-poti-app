"""Serviço de Domínio para Controle de Gastos e Orçamento Mensal.

Isolado de qualquer framework de mensageria (Telegram, WhatsApp, CLI, etc.),
permitindo fácil reutilização e alta testabilidade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

import pymysql
from pymysql.cursors import DictCursor

from src.config import DatabaseConfig
from src.db import get_db_connection
from src.exceptions import (
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
)
from src.utils.money import slugify, to_decimal, validate_month_ref


class BudgetService:
    """Implementa as regras de negócio de planejamento e gastos mensais."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None) -> None:
        self.db_config = db_config

    # -------------------------------------------------------------------------
    # Métodos de Planejamento Mensal
    # -------------------------------------------------------------------------

    def get_or_create_month_plan(
        self,
        month_ref: Optional[str] = None,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Recupera o planejamento do mês ou cria automaticamente a partir dos padrões.
        
        Se o mês não existir em monthly_plans, cria o registro utilizando default_salary
        e a soma dos tópicos ativos (ou default_spending_limit, se configurado).
        """
        valid_month = validate_month_ref(month_ref)

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            with connection.cursor(DictCursor) as cursor:
                # 1. Verifica se já existe plano para o mês
                cursor.execute(
                    """
                    SELECT id, month_ref, salary, spending_limit, created_at, updated_at
                    FROM monthly_plans
                    WHERE month_ref = %s
                    FOR UPDATE
                    """,
                    (valid_month,),
                )
                existing = cursor.fetchone()
                if existing:
                    return {
                        "id": existing["id"],
                        "month_ref": existing["month_ref"],
                        "salary": Decimal(str(existing["salary"])),
                        "spending_limit": Decimal(str(existing["spending_limit"])),
                        "created_at": existing["created_at"],
                        "updated_at": existing["updated_at"],
                    }

                # 2. Busca configurações globais padrão
                cursor.execute(
                    """
                    SELECT default_salary, default_spending_limit
                    FROM app_settings
                    ORDER BY id ASC
                    LIMIT 1
                    """
                )
                settings = cursor.fetchone()

                default_salary = (
                    Decimal(str(settings["default_salary"]))
                    if settings and settings["default_salary"] is not None
                    else Decimal("1800.00")
                )
                default_spending_limit = (
                    Decimal(str(settings["default_spending_limit"]))
                    if settings and settings["default_spending_limit"] is not None
                    else None
                )

                # 3. Determina o limite de gastos (específico ou soma dos tópicos ativos)
                if default_spending_limit is not None and default_spending_limit > Decimal("0.00"):
                    spending_limit = default_spending_limit
                else:
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(planned_amount), 0.00) AS total_planned
                        FROM categories
                        WHERE is_active = 1
                        """
                    )
                    cat_sum = cursor.fetchone()
                    total_planned = Decimal(str(cat_sum["total_planned"])) if cat_sum else Decimal("0.00")
                    spending_limit = total_planned if total_planned > Decimal("0.00") else default_salary

                # 4. Cria o plano para o novo mês
                cursor.execute(
                    """
                    INSERT INTO monthly_plans (month_ref, salary, spending_limit)
                    VALUES (%s, %s, %s)
                    """,
                    (valid_month, default_salary, spending_limit),
                )
                new_id = cursor.lastrowid

                return {
                    "id": new_id,
                    "month_ref": valid_month,
                    "salary": default_salary,
                    "spending_limit": spending_limit,
                    "created_at": None,
                    "updated_at": None,
                }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    def set_salary(
        self,
        amount: Union[str, Decimal, float],
        month_ref: Optional[str] = None,
        update_default: bool = True,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Atualiza o salário do mês especificado e opcionalmente o valor padrão futuro."""
        dec_amount = to_decimal(amount, allow_negative=False, allow_zero=False)
        valid_month = validate_month_ref(month_ref)

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            # Garante que o mês existe antes da atualização
            self.get_or_create_month_plan(valid_month, conn=connection)

            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    """
                    UPDATE monthly_plans
                    SET salary = %s
                    WHERE month_ref = %s
                    """,
                    (dec_amount, valid_month),
                )

                if update_default:
                    # Atualiza ou insere na tabela app_settings
                    cursor.execute(
                        """
                        INSERT INTO app_settings (id, default_salary)
                        VALUES (1, %s)
                        ON DUPLICATE KEY UPDATE default_salary = VALUES(default_salary)
                        """,
                        (dec_amount,),
                    )

                cursor.execute(
                    """
                    SELECT id, month_ref, salary, spending_limit
                    FROM monthly_plans
                    WHERE month_ref = %s
                    """,
                    (valid_month,),
                )
                updated = cursor.fetchone()

                return {
                    "id": updated["id"],
                    "month_ref": updated["month_ref"],
                    "salary": Decimal(str(updated["salary"])),
                    "spending_limit": Decimal(str(updated["spending_limit"])),
                    "default_updated": update_default,
                }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    def set_spending_limit(
        self,
        amount: Union[str, Decimal, float],
        month_ref: Optional[str] = None,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Altera o teto/limite de gastos total para o mês especificado."""
        dec_amount = to_decimal(amount, allow_negative=False, allow_zero=False)
        valid_month = validate_month_ref(month_ref)

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            self.get_or_create_month_plan(valid_month, conn=connection)

            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    """
                    UPDATE monthly_plans
                    SET spending_limit = %s
                    WHERE month_ref = %s
                    """,
                    (dec_amount, valid_month),
                )

                cursor.execute(
                    """
                    SELECT id, month_ref, salary, spending_limit
                    FROM monthly_plans
                    WHERE month_ref = %s
                    """,
                    (valid_month,),
                )
                updated = cursor.fetchone()

                return {
                    "id": updated["id"],
                    "month_ref": updated["month_ref"],
                    "salary": Decimal(str(updated["salary"])),
                    "spending_limit": Decimal(str(updated["spending_limit"])),
                }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    # -------------------------------------------------------------------------
    # Métodos de Gerenciamento de Categorias (Tópicos)
    # -------------------------------------------------------------------------

    def upsert_category(
        self,
        name: str,
        planned_amount: Union[str, Decimal, float],
        monthly_limit: Optional[Union[str, Decimal, float]] = None,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Cria um novo tópico ou atualiza o valor planejado/teto de um existente."""
        clean_name = name.strip()
        slug = slugify(clean_name)
        dec_planned = to_decimal(planned_amount, allow_negative=False, allow_zero=True)
        dec_limit = (
            to_decimal(monthly_limit, allow_negative=False, allow_zero=True)
            if monthly_limit is not None
            else None
        )

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT id, slug, name, planned_amount, monthly_limit, is_active
                    FROM categories
                    WHERE slug = %s
                    FOR UPDATE
                    """,
                    (slug,),
                )
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """
                        UPDATE categories
                        SET name = %s,
                            planned_amount = %s,
                            monthly_limit = %s,
                            is_active = 1
                        WHERE id = %s
                        """,
                        (clean_name, dec_planned, dec_limit, existing["id"]),
                    )
                    cat_id = existing["id"]
                    action = "updated"
                else:
                    cursor.execute(
                        """
                        INSERT INTO categories (slug, name, planned_amount, monthly_limit, is_active)
                        VALUES (%s, %s, %s, %s, 1)
                        """,
                        (slug, clean_name, dec_planned, dec_limit),
                    )
                    cat_id = cursor.lastrowid
                    action = "created"

                return {
                    "id": cat_id,
                    "slug": slug,
                    "name": clean_name,
                    "planned_amount": dec_planned,
                    "monthly_limit": dec_limit,
                    "is_active": 1,
                    "action": action,
                }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    def rename_category(
        self,
        old_slug: str,
        new_name: str,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Renomeia uma categoria preservando seu ID para integridade histórica de transações."""
        clean_new_name = new_name.strip()
        new_slug = slugify(clean_new_name)
        target_slug = slugify(old_slug)

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            with connection.cursor(DictCursor) as cursor:
                # 1. Verifica se a categoria antiga existe
                cursor.execute(
                    """
                    SELECT id, slug, name, planned_amount, monthly_limit, is_active
                    FROM categories
                    WHERE slug = %s
                    FOR UPDATE
                    """,
                    (target_slug,),
                )
                category = cursor.fetchone()
                if not category:
                    raise CategoryNotFoundError(target_slug)

                # 2. Se o novo slug for diferente, verifica se colide com outra categoria existente
                if new_slug != target_slug:
                    cursor.execute(
                        """
                        SELECT id
                        FROM categories
                        WHERE slug = %s AND id != %s
                        """,
                        (new_slug, category["id"]),
                    )
                    collision = cursor.fetchone()
                    if collision:
                        raise CategoryAlreadyExistsError(new_slug)

                cursor.execute(
                    """
                    UPDATE categories
                    SET name = %s, slug = %s
                    WHERE id = %s
                    """,
                    (clean_new_name, new_slug, category["id"]),
                )

                return {
                    "id": category["id"],
                    "old_slug": target_slug,
                    "new_slug": new_slug,
                    "name": clean_new_name,
                    "planned_amount": Decimal(str(category["planned_amount"])),
                    "monthly_limit": (
                        Decimal(str(category["monthly_limit"]))
                        if category["monthly_limit"] is not None
                        else None
                    ),
                    "is_active": category["is_active"],
                }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    def deactivate_category(
        self,
        slug: str,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Desativa uma categoria (soft delete), preservando todo o histórico financeiro."""
        target_slug = slugify(slug)

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            with connection.cursor(DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT id, slug, name, planned_amount, monthly_limit, is_active
                    FROM categories
                    WHERE slug = %s
                    FOR UPDATE
                    """,
                    (target_slug,),
                )
                category = cursor.fetchone()
                if not category:
                    raise CategoryNotFoundError(target_slug)

                cursor.execute(
                    """
                    UPDATE categories
                    SET is_active = 0
                    WHERE id = %s
                    """,
                    (category["id"],),
                )

                return {
                    "id": category["id"],
                    "slug": target_slug,
                    "name": category["name"],
                    "planned_amount": Decimal(str(category["planned_amount"])),
                    "monthly_limit": (
                        Decimal(str(category["monthly_limit"]))
                        if category["monthly_limit"] is not None
                        else None
                    ),
                    "is_active": 0,
                }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    # -------------------------------------------------------------------------
    # Métodos de Lançamentos e Despesas
    # -------------------------------------------------------------------------

    def add_expense(
        self,
        category_slug: str,
        amount: Union[str, Decimal, float],
        description: Optional[str] = None,
        month_ref: Optional[str] = None,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Registra um gasto em transactions e retorna o status detalhado com alertas."""
        target_slug = slugify(category_slug)
        dec_amount = to_decimal(amount, allow_negative=False, allow_zero=False)
        valid_month = validate_month_ref(month_ref)
        clean_description = description.strip() if description else None

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            # 1. Garante que o plano do mês existe
            plan = self.get_or_create_month_plan(valid_month, conn=connection)

            with connection.cursor(DictCursor) as cursor:
                # 2. Localiza a categoria
                cursor.execute(
                    """
                    SELECT id, slug, name, planned_amount, monthly_limit, is_active
                    FROM categories
                    WHERE slug = %s
                    """,
                    (target_slug,),
                )
                category = cursor.fetchone()
                if not category:
                    raise CategoryNotFoundError(target_slug)

                category_id = category["id"]

                # 3. Insere a transação
                cursor.execute(
                    """
                    INSERT INTO transactions (category_id, month_ref, amount, description)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (category_id, valid_month, dec_amount, clean_description),
                )
                tx_id = cursor.lastrowid

                # 4. Total gasto na categoria no mês atual
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0.00) AS cat_spent
                    FROM transactions
                    WHERE category_id = %s AND month_ref = %s
                    """,
                    (category_id, valid_month),
                )
                cat_spent_row = cursor.fetchone()
                category_spent = Decimal(str(cat_spent_row["cat_spent"])) if cat_spent_row else Decimal("0.00")

                # 5. Total geral gasto no mês
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(amount), 0.00) AS total_month_spent
                    FROM transactions
                    WHERE month_ref = %s
                    """,
                    (valid_month,),
                )
                total_row = cursor.fetchone()
                total_spent = Decimal(str(total_row["total_month_spent"])) if total_row else Decimal("0.00")

            salary = plan["salary"]
            spending_limit = plan["spending_limit"]
            cat_planned = Decimal(str(category["planned_amount"]))
            cat_limit = (
                Decimal(str(category["monthly_limit"]))
                if category["monthly_limit"] is not None
                else cat_planned
            )

            remaining_limit = spending_limit - total_spent
            remaining_salary = salary - total_spent
            cat_remaining = cat_limit - category_spent

            # Alertas gerais do mês
            warning_80 = total_spent >= (spending_limit * Decimal("0.80"))
            warning_100 = total_spent >= spending_limit

            # Alertas específicos do tópico
            cat_warning_80 = category_spent >= (cat_limit * Decimal("0.80")) if cat_limit > Decimal("0.00") else False
            cat_warning_100 = category_spent >= cat_limit if cat_limit > Decimal("0.00") else False

            return {
                "transaction_id": tx_id,
                "amount": dec_amount,
                "description": clean_description,
                "month_ref": valid_month,
                "category": {
                    "id": category_id,
                    "slug": category["slug"],
                    "name": category["name"],
                    "planned_amount": cat_planned,
                    "monthly_limit": category["monthly_limit"],
                    "effective_limit": cat_limit,
                    "total_spent": category_spent,
                    "remaining": cat_remaining,
                    "warning_80": cat_warning_80,
                    "warning_100": cat_warning_100,
                },
                "monthly_plan": {
                    "salary": salary,
                    "spending_limit": spending_limit,
                    "total_spent": total_spent,
                    "remaining_limit": remaining_limit,
                    "remaining_salary": remaining_salary,
                },
                "warning_80": warning_80,
                "warning_100": warning_100,
            }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)

    # -------------------------------------------------------------------------
    # Métodos de Relatório e Visão Geral
    # -------------------------------------------------------------------------

    def get_monthly_summary(
        self,
        month_ref: Optional[str] = None,
        conn: Optional[pymysql.Connection] = None,
    ) -> Dict[str, Any]:
        """Retorna visão analítica completa do mês: salário, teto, total gasto e breakdown por tópico."""
        valid_month = validate_month_ref(month_ref)

        def _execute(connection: pymysql.Connection) -> Dict[str, Any]:
            plan = self.get_or_create_month_plan(valid_month, conn=connection)

            with connection.cursor(DictCursor) as cursor:
                # Busca categorias ativas OU categorias inativas que possuem transações no mês selecionado
                cursor.execute(
                    """
                    SELECT 
                        c.id,
                        c.slug,
                        c.name,
                        c.planned_amount,
                        c.monthly_limit,
                        c.is_active,
                        COALESCE(t.total_spent, 0.00) AS total_spent,
                        COALESCE(t.tx_count, 0) AS tx_count
                    FROM categories c
                    LEFT JOIN (
                        SELECT 
                            category_id,
                            SUM(amount) AS total_spent,
                            COUNT(id) AS tx_count
                        FROM transactions
                        WHERE month_ref = %s
                        GROUP BY category_id
                    ) t ON c.id = t.category_id
                    WHERE c.is_active = 1 OR t.total_spent > 0
                    ORDER BY c.is_active DESC, total_spent DESC, c.name ASC
                    """,
                    (valid_month,),
                )
                categories_data = cursor.fetchall()

            salary = plan["salary"]
            spending_limit = plan["spending_limit"]

            categories_summary: List[Dict[str, Any]] = []
            total_spent = Decimal("0.00")

            for row in categories_data:
                spent = Decimal(str(row["total_spent"]))
                planned = Decimal(str(row["planned_amount"]))
                limit = (
                    Decimal(str(row["monthly_limit"]))
                    if row["monthly_limit"] is not None
                    else planned
                )
                total_spent += spent

                remaining = limit - spent
                pct_used = (spent / limit * Decimal("100.00")) if limit > Decimal("0.00") else Decimal("0.00")

                categories_summary.append(
                    {
                        "id": row["id"],
                        "slug": row["slug"],
                        "name": row["name"],
                        "planned_amount": planned,
                        "monthly_limit": row["monthly_limit"],
                        "effective_limit": limit,
                        "total_spent": spent,
                        "remaining": remaining,
                        "usage_pct": round(pct_used, 2),
                        "tx_count": int(row["tx_count"]),
                        "is_active": bool(row["is_active"]),
                    }
                )

            remaining_salary = salary - total_spent
            remaining_limit = spending_limit - total_spent

            limit_usage_pct = (
                (total_spent / spending_limit * Decimal("100.00"))
                if spending_limit > Decimal("0.00")
                else Decimal("0.00")
            )
            salary_usage_pct = (
                (total_spent / salary * Decimal("100.00"))
                if salary > Decimal("0.00")
                else Decimal("0.00")
            )

            return {
                "month_ref": valid_month,
                "salary": salary,
                "spending_limit": spending_limit,
                "total_spent": total_spent,
                "remaining_salary": remaining_salary,
                "remaining_limit": remaining_limit,
                "limit_usage_pct": round(limit_usage_pct, 2),
                "salary_usage_pct": round(salary_usage_pct, 2),
                "warning_80": total_spent >= (spending_limit * Decimal("0.80")),
                "warning_100": total_spent >= spending_limit,
                "categories": categories_summary,
            }

        if conn is not None:
            return _execute(conn)
        with get_db_connection(self.db_config) as managed_conn:
            return _execute(managed_conn)
