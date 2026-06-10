#!/bin/bash
echo "🔧 Fixing QRMANITY admin role in NocoBase..."

# Check if QRMANITY exists
USER_EXISTS=$(docker exec qumanity_postgres psql -U postgres -d qumanity_crm -t -c "SELECT COUNT(*) FROM users WHERE nickname = 'QRMANITY' OR username = 'QRMANITY';" | tr -d ' ')

if [ "$USER_EXISTS" = "0" ]; then
    echo "❌ User 'QRMANITY' not found in database."
    echo "   Please create the account first at http://localhost:3000"
    echo "   Use username: QRMANITY"
    exit 1
fi

echo "✅ User QRMANITY found"

# Create root role if not exists
docker exec qumanity_postgres psql -U postgres -d qumanity_crm -c "
INSERT INTO roles (name, title, description, \"createdAt\", \"updatedAt\")
SELECT 'root', 'Root', 'Super Administrator', NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'root');
"

# Assign root role to QRMANITY
docker exec qumanity_postgres psql -U postgres -d qumanity_crm -c "
INSERT INTO \"rolesUsers\" (\"userId\", \"roleId\", \"createdAt\", \"updatedAt\")
SELECT u.id, r.id, NOW(), NOW()
FROM users u
CROSS JOIN roles r
WHERE (u.nickname = 'QRMANITY' OR u.username = 'QRMANITY')
  AND r.name = 'root'
ON CONFLICT (\"userId\", \"roleId\") DO NOTHING;
"

echo "✅ Root role assigned to QRMANITY"

# Verify
echo ""
echo "📊 Verification:"
docker exec qumanity_postgres psql -U postgres -d qumanity_crm -c "
SELECT u.id, u.nickname, u.username, u.email, r.name as role_name
FROM users u
LEFT JOIN \"rolesUsers\" ru ON ru.\"userId\" = u.id
LEFT JOIN roles r ON r.id = ru.\"roleId\"
WHERE u.nickname = 'QRMANITY' OR u.username = 'QRMANITY';
"

# Run upgrade to sync permissions
echo ""
echo "🔄 Running NocoBase upgrade..."
docker exec qumanity_nocobase sh -c 'yarn nocobase upgrade 2>/dev/null || npx nocobase upgrade 2>/dev/null'

# Restart
echo "🔄 Restarting NocoBase..."
docker compose -f docker-compose.nocobase.yml restart nocobase

echo ""
echo "✅ Setup complete!"
echo "   Clear browser cache and login at http://localhost:3000"
echo "   Username: QRMANITY"
