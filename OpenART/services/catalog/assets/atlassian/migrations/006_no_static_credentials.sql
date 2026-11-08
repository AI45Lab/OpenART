-- Only passwords verified at login authenticate users.
--
-- 1. Static/opaque bearer tokens are gone: drop the compatibility table that
--    mapped fixed `tok_*` credentials to users.
-- 2. The default tenant is the baseline template. Its users own the demo
--    catalog and must not be able to log in (init-tenant copies them into
--    every task tenant). '!no-login' is NO_LOGIN_PASSWORD_HASH in
--    app/backend/src/auth/passwords.js; no password hashes to it.
--
-- Idempotent: safe to re-run on every start.
DROP TABLE IF EXISTS legacy_access_tokens;

UPDATE app_user SET password_hash = '!no-login'
 WHERE tenant_id = 'default' AND password_hash <> '!no-login';
