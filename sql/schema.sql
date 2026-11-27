-- =============================================================================
-- Schema: Sistema de Controle de Gastos Mensais
-- MySQL 8.0+ compatível
-- =============================================================================

CREATE DATABASE IF NOT EXISTS expense_control
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE expense_control;

-- -----------------------------------------------------------------------------
-- Tabela: app_settings
-- Armazena configurações padrão globais para replicação em novos meses
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    default_salary DECIMAL(10, 2) NOT NULL DEFAULT 1800.00,
    default_spending_limit DECIMAL(10, 2) NULL COMMENT 'Se NULL, o teto é derivado da soma dos tópicos ativos',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- Tabela: categories
-- Tópicos de gastos planejados com suporte a soft delete (is_active)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    planned_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    monthly_limit DECIMAL(10, 2) NULL COMMENT 'Teto específico para o tópico, se houver',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_categories_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- Tabela: monthly_plans
-- Planejamento financeiro específico de cada mês (ex: 2026-11)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monthly_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    month_ref CHAR(7) NOT NULL UNIQUE COMMENT 'Formato YYYY-MM',
    salary DECIMAL(10, 2) NOT NULL,
    spending_limit DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_monthly_plans_month (month_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- Tabela: transactions
-- Registro individual de lançamentos de despesas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    month_ref CHAR(7) NOT NULL COMMENT 'Formato YYYY-MM para particionamento lógico',
    amount DECIMAL(10, 2) NOT NULL,
    description VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
    INDEX idx_transactions_month (month_ref),
    INDEX idx_transactions_category_month (category_id, month_ref),
    INDEX idx_transactions_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
