"""Bateria de testes unitários para BudgetService e utilitários de domínio."""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.exceptions import (
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    InvalidAmountError,
    InvalidMonthRefError,
)
from src.services.budget_service import BudgetService
from src.utils.money import format_brl, slugify, to_decimal, validate_month_ref


class TestMoneyUtils(unittest.TestCase):
    def test_to_decimal_valid_strings(self):
        self.assertEqual(to_decimal("284,71"), Decimal("284.71"))
        self.assertEqual(to_decimal("284.71"), Decimal("284.71"))
        self.assertEqual(to_decimal("R$ 1.800,00"), Decimal("1800.00"))
        self.assertEqual(to_decimal("1.234,56"), Decimal("1234.56"))
        self.assertEqual(to_decimal("1,234.56"), Decimal("1234.56"))
        self.assertEqual(to_decimal(100), Decimal("100.00"))
        self.assertEqual(to_decimal(59.9), Decimal("59.90"))

    def test_to_decimal_invalid_values(self):
        with self.assertRaises(InvalidAmountError):
            to_decimal("invalido")
        with self.assertRaises(InvalidAmountError):
            to_decimal("-50.00", allow_negative=False)
        with self.assertRaises(InvalidAmountError):
            to_decimal("0.00", allow_zero=False)

    def test_format_brl(self):
        self.assertEqual(format_brl(Decimal("1800.00")), "R$ 1.800,00")
        self.assertEqual(format_brl(Decimal("284.71")), "R$ 284,71")
        self.assertEqual(format_brl(Decimal("-10.50")), "R$ -10,50")
        self.assertEqual(format_brl(None), "R$ 0,00")

    def test_slugify(self):
        self.assertEqual(slugify("Faculdade"), "faculdade")
        self.assertEqual(slugify("Prestação Carro"), "prestacao-carro")
        self.assertEqual(slugify("Água & Luz"), "agua-luz")
        self.assertEqual(slugify("  Netflix   "), "netflix")

    def test_validate_month_ref(self):
        self.assertEqual(validate_month_ref("2026-11"), "2026-11")
        with self.assertRaises(InvalidMonthRefError):
            validate_month_ref("2026-13")
        with self.assertRaises(InvalidMonthRefError):
            validate_month_ref("nov-2026")


class TestBudgetService(unittest.TestCase):
    def setUp(self):
        self.service = BudgetService()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor

    def test_get_or_create_month_plan_existing(self):
        self.mock_cursor.fetchone.return_value = {
            "id": 1,
            "month_ref": "2026-11",
            "salary": 1800.00,
            "spending_limit": 1019.61,
            "created_at": None,
            "updated_at": None,
        }
        res = self.service.get_or_create_month_plan("2026-11", conn=self.mock_conn)
        self.assertEqual(res["month_ref"], "2026-11")
        self.assertEqual(res["salary"], Decimal("1800.00"))
        self.assertEqual(res["spending_limit"], Decimal("1019.61"))

    def test_get_or_create_month_plan_new_month(self):
        # 1o fetchone: plano não existe
        # 2o fetchone: app_settings (default_salary=1800, default_spending_limit=None)
        # 3o fetchone: categories sum = 1019.61
        self.mock_cursor.fetchone.side_effect = [
            None,
            {"default_salary": 1800.00, "default_spending_limit": None},
            {"total_planned": 1019.61},
        ]
        self.mock_cursor.lastrowid = 10
        res = self.service.get_or_create_month_plan("2026-12", conn=self.mock_conn)
        self.assertEqual(res["id"], 10)
        self.assertEqual(res["salary"], Decimal("1800.00"))
        self.assertEqual(res["spending_limit"], Decimal("1019.61"))

    def test_set_salary(self):
        # Mock do get_or_create_month_plan interno
        with patch.object(self.service, "get_or_create_month_plan") as mock_get_plan:
            mock_get_plan.return_value = {"id": 1, "month_ref": "2026-11", "salary": Decimal("1800.00")}
            self.mock_cursor.fetchone.return_value = {
                "id": 1,
                "month_ref": "2026-11",
                "salary": 2000.00,
                "spending_limit": 1019.61,
            }
            res = self.service.set_salary("2000.00", month_ref="2026-11", update_default=True, conn=self.mock_conn)
            self.assertEqual(res["salary"], Decimal("2000.00"))
            self.assertTrue(res["default_updated"])

    def test_upsert_category_new(self):
        self.mock_cursor.fetchone.return_value = None
        self.mock_cursor.lastrowid = 5
        res = self.service.upsert_category("Prestação Carro", "600,00", conn=self.mock_conn)
        self.assertEqual(res["slug"], "prestacao-carro")
        self.assertEqual(res["planned_amount"], Decimal("600.00"))
        self.assertEqual(res["action"], "created")

    def test_rename_category_not_found(self):
        self.mock_cursor.fetchone.return_value = None
        with self.assertRaises(CategoryNotFoundError):
            self.service.rename_category("slug-inexistente", "Novo Nome", conn=self.mock_conn)

    def test_rename_category_collision(self):
        # 1o fetchone: acha categoria atual com id=1
        # 2o fetchone: acha categoria existente com o mesmo new_slug e id=2
        self.mock_cursor.fetchone.side_effect = [
            {"id": 1, "slug": "gasolina", "name": "Gasolina", "planned_amount": 200, "monthly_limit": None, "is_active": 1},
            {"id": 2},
        ]
        with self.assertRaises(CategoryAlreadyExistsError):
            self.service.rename_category("gasolina", "Combustível", conn=self.mock_conn)

    def test_add_expense_with_alerts(self):
        with patch.object(self.service, "get_or_create_month_plan") as mock_plan:
            mock_plan.return_value = {
                "salary": Decimal("1800.00"),
                "spending_limit": Decimal("1000.00"),
            }
            # 1o fetchone: category (gasolina, limit=200)
            # 2o fetchone: cat_spent = 180.00
            # 3o fetchone: total_month_spent = 850.00 (>= 80% do limite de 1000)
            self.mock_cursor.fetchone.side_effect = [
                {"id": 2, "slug": "gasolina", "name": "Gasolina", "planned_amount": 200.00, "monthly_limit": 200.00, "is_active": 1},
                {"cat_spent": 180.00},
                {"total_month_spent": 850.00},
            ]
            self.mock_cursor.lastrowid = 101

            res = self.service.add_expense("gasolina", "50.00", "Posto Ipiranga", "2026-11", conn=self.mock_conn)
            self.assertEqual(res["transaction_id"], 101)
            self.assertEqual(res["amount"], Decimal("50.00"))
            self.assertTrue(res["warning_80"])
            self.assertFalse(res["warning_100"])
            self.assertEqual(res["monthly_plan"]["remaining_limit"], Decimal("150.00"))
            self.assertEqual(res["monthly_plan"]["remaining_salary"], Decimal("950.00"))


if __name__ == "__main__":
    unittest.main()
