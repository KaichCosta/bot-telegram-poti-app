-- =============================================================================
-- Seed: Dados Iniciais do Sistema de Controle de Gastos
-- =============================================================================

USE expense_control;

-- Configuração inicial padrão (Salário base R$ 1.800,00)
INSERT INTO app_settings (id, default_salary, default_spending_limit)
VALUES (1, 1800.00, NULL)
ON DUPLICATE KEY UPDATE
    default_salary = VALUES(default_salary);

-- Tópicos (categorias) iniciais de planejamento mensal
-- Soma base inicial = R$ 1.019,61
INSERT INTO categories (slug, name, planned_amount, monthly_limit, is_active)
VALUES
    ('faculdade', 'Faculdade', 284.71, 284.71, 1),
    ('gasolina',  'Gasolina',  200.00, 200.00, 1),
    ('cabelo',    'Cabelo',    120.00, 120.00, 1),
    ('namorada',  'Namorada',  255.00, 255.00, 1),
    ('merenda',   'Merenda',   100.00, 100.00, 1),
    ('netflix',   'Netflix',    59.90,  59.90, 1)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    planned_amount = VALUES(planned_amount),
    monthly_limit = VALUES(monthly_limit),
    is_active = 1;
