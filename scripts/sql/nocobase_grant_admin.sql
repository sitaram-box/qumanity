-- Grant NocoBase root/admin role to QRMANITY (or edit the username below).
-- Run manually:
--   docker exec -i qumanity_postgres psql -U postgres -d qumanity_crm < scripts/sql/nocobase_grant_admin.sql

\set admin_user 'QRMANITY'

DO $$
DECLARE
  v_user_id   integer;
  v_role_id   integer;
  v_junction  text;
  v_role_name text;
BEGIN
  SELECT id INTO v_user_id
  FROM users
  WHERE nickname ILIKE :'admin_user'
     OR username ILIKE :'admin_user'
  ORDER BY id
  LIMIT 1;

  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'User % not found', :'admin_user';
  END IF;

  SELECT id, name INTO v_role_id, v_role_name
  FROM roles
  WHERE name IN ('root', 'admin')
  ORDER BY CASE name WHEN 'root' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END
  LIMIT 1;

  IF v_role_id IS NULL THEN
    RAISE EXCEPTION 'No root/admin role found in roles table';
  END IF;

  SELECT table_name INTO v_junction
  FROM information_schema.tables
  WHERE table_schema = 'public'
    AND table_name IN ('rolesUsers', 'roles_users')
  LIMIT 1;

  IF v_junction = 'rolesUsers' THEN
    INSERT INTO "rolesUsers" ("userId", "roleId", "createdAt", "updatedAt")
    VALUES (v_user_id, v_role_id, NOW(), NOW())
    ON CONFLICT ("userId", "roleId") DO NOTHING;
  ELSIF v_junction = 'roles_users' THEN
    INSERT INTO roles_users (user_id, role_id, created_at, updated_at)
    VALUES (v_user_id, v_role_id, NOW(), NOW())
    ON CONFLICT (user_id, role_id) DO NOTHING;
  ELSE
    RAISE EXCEPTION 'rolesUsers junction table not found';
  END IF;

  RAISE NOTICE 'User % (id=%) → role % (id=%)', :'admin_user', v_user_id, v_role_name, v_role_id;
END $$;

-- Verify
SELECT u.nickname, u.username, u.email, r.name AS role_name, r.title AS role_title
FROM users u
LEFT JOIN "rolesUsers" ru ON ru."userId" = u.id
LEFT JOIN roles r ON r.id = ru."roleId"
WHERE u.nickname ILIKE :'admin_user' OR u.username ILIKE :'admin_user';
