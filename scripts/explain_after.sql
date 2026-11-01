-- Lab 7: плани виконання запитів НОВОГО коду (ПІСЛЯ оптимізації та додавання індексів)
-- Запуск: Get-Content scripts/explain_after.sql | docker compose -p petitions-lab7 exec -T db psql -U petitions -d petitions
ANALYZE;

\echo '=== 1. GET /petitions/1 : один запит, кількість голосів рахує COUNT() у БД ==='
EXPLAIN ANALYZE
SELECT petitions.*, users.username,
       (SELECT count(votes.id) FROM votes WHERE votes.petition_id = petitions.id) AS votes_count
FROM petitions LEFT OUTER JOIN users ON users.id = petitions.author_id
WHERE petitions.id = 1;

\echo '=== 2. GET /petitions/ : каталог (індекс ix_petitions_created_at + COUNT для кожної петиції) ==='
EXPLAIN ANALYZE
SELECT petitions.*, users.username,
       (SELECT count(votes.id) FROM votes WHERE votes.petition_id = petitions.id) AS votes_count
FROM petitions LEFT OUTER JOIN users ON users.id = petitions.author_id
ORDER BY petitions.created_at DESC;

\echo '=== 3. POST /petitions/1/vote : перевірка дубліката (складений індекс ix_votes_petition_user) ==='
EXPLAIN ANALYZE
SELECT * FROM votes
WHERE votes.petition_id = 1 AND (votes.voter_signature_hash = 'abc' OR votes.user_id = 2);

\echo '=== 4. Список індексів таблиць ==='
SELECT tablename, indexname, indexdef FROM pg_indexes WHERE tablename IN ('petitions', 'votes') ORDER BY 1, 2;
