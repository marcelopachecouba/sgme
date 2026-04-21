-- vendas por vendedor: quantidade de pagamentos pagos + valor total
SELECT
    p.vendedor_codigo,
    v.nome AS vendedor_nome,
    e.nome AS equipe_nome,
    COALESCE(SUM(p.quantidade_rifas), 0) AS quantidade_rifas,
    COALESCE(SUM(p.valor_total), 0) AS valor_total
FROM pagamentos p
LEFT JOIN vendedores v ON v.codigo = p.vendedor_codigo
LEFT JOIN equipes e ON e.id = p.equipe_id
WHERE p.status = 'pago'
GROUP BY p.vendedor_codigo, v.nome, e.nome
ORDER BY valor_total DESC, quantidade_rifas DESC;

-- vendas por equipe: total financeiro e quantidade de pagamentos pagos
SELECT
    e.id AS equipe_id,
    e.nome AS equipe_nome,
    COALESCE(SUM(p.quantidade_rifas), 0) AS quantidade_rifas,
    COALESCE(SUM(p.valor_total), 0) AS valor_total
FROM equipes e
LEFT JOIN pagamentos p
    ON p.equipe_id = e.id
   AND p.status = 'pago'
GROUP BY e.id, e.nome
ORDER BY valor_total DESC, quantidade_rifas DESC;

-- ranking geral: equipe + vendedor ordenado por valor
SELECT
    e.nome AS equipe_nome,
    v.nome AS vendedor_nome,
    v.codigo AS vendedor_codigo,
    COALESCE(SUM(p.quantidade_rifas), 0) AS quantidade_rifas,
    COALESCE(SUM(p.valor_total), 0) AS valor_total
FROM pagamentos p
JOIN vendedores v ON v.codigo = p.vendedor_codigo
JOIN equipes e ON e.id = p.equipe_id
WHERE p.status = 'pago'
GROUP BY e.nome, v.nome, v.codigo
ORDER BY valor_total DESC, quantidade_rifas DESC, vendedor_nome ASC;
