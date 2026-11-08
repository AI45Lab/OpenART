-- Original seed rows use explicit label IDs. Align their sequence before
-- the first namespace copy on a populated legacy volume. Never lower it.
SELECT setval(pg_get_serial_sequence('label', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 0) FROM label),
             (SELECT last_value FROM label_id_seq), 1));
