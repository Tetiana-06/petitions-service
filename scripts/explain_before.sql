-- Lab 7: плани виконання запитів, які генерує СТАРИЙ код (ДО оптимізації)
-- Запуск: Get-Content scripts/explain_before.sql | docker compose -p petitions-lab7 exec -T db psql -U petitions -d petitions
ANALYZE;

\echo '=== 1. GET /petitions/1 : selectinload(Petition.votes) тягне ВСІ голоси петиції, щоб порахувати len() ==='
EXPLAIN ANALYZE
SELECT votes.petition_id, votes.id, votes.user_id, votes.voter_signature_hash, votes.voted_at
FROM votes WHERE votes.petition_id IN (1);

\echo '=== 2. GET /petitions/ : каталог без індексу на created_at ==='
EXPLAIN ANALYZE
SELECT * FROM petitions ORDER BY created_at DESC;

\echo '=== 3. GET /petitions/ : selectinload тягне голоси ВСІХ петицій ==='
EXPLAIN ANALYZE
SELECT votes.petition_id, votes.id, votes.user_id, votes.voter_signature_hash, votes.voted_at
FROM votes WHERE votes.petition_id IN (SELECT id FROM petitions);

\echo '=== 4. POST /petitions/1/vote : перевірка дубліката голосу ==='
EXPLAIN ANALYZE
SELECT * FROM votes
WHERE votes.petition_id = 1 AND (votes.voter_signature_hash = 'abc' OR votes.user_id = 2);
