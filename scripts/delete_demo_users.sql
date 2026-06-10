-- Delete listed demo user accounts (preserves H_U_ADMIN).
-- Run: sqlite3 indiaq.db < scripts/delete_demo_users.sql

BEGIN TRANSACTION;

-- Demo private IDs to remove
CREATE TEMP TABLE IF NOT EXISTS demo_users (private_id TEXT PRIMARY KEY);
DELETE FROM demo_users;
INSERT INTO demo_users (private_id) VALUES
  ('I4U9-DU-F-Y-ZL-HKG'),
  ('RR8-DU-GM-AB-WS-CAN'),
  ('T24-DU-GF-AY-AA-SS.TS.2.E.2'),
  ('MRXU-PM-GM-AV-FA-NS.HR.11.3.A9'),
  ('NV41-DU-GM-AY-FS-CS.JK.1.5.33'),
  ('DMG3-DU-GM-AB-FA-ES.JH.11.D.F'),
  ('380373241'),
  ('NKEC-DU-GF-AB-WC-CS.JK.B.3.11');

-- Connection requests
DELETE FROM connection_requests
 WHERE from_user_private_id IN (SELECT private_id FROM demo_users)
    OR to_user_private_id IN (SELECT private_id FROM demo_users);

-- Messages (sender_id / recipient_id)
DELETE FROM messages
 WHERE sender_id IN (SELECT private_id FROM demo_users)
    OR recipient_id IN (SELECT private_id FROM demo_users);

-- Post votes and posts
DELETE FROM post_votes
 WHERE voter_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM posts
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

-- Family graph (member ids first, then profiles)
DELETE FROM family_relationships
 WHERE source_id IN (
         SELECT id FROM family_members
          WHERE user_private_id IN (SELECT private_id FROM demo_users)
       )
    OR target_id IN (
         SELECT id FROM family_members
          WHERE user_private_id IN (SELECT private_id FROM demo_users)
       );

DELETE FROM family_members
 WHERE user_private_id IN (SELECT private_id FROM demo_users)
    OR member_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM family_profile
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

-- Elections
DELETE FROM election_votes
 WHERE voter_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM election_candidates
 WHERE candidate_private_id IN (SELECT private_id FROM demo_users);

-- Qoin / wallets / accounts
DELETE FROM qoin_transactions
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM wallets
 WHERE owner_type = 'user'
   AND owner_id IN (SELECT private_id FROM demo_users);

DELETE FROM user_accounts
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

-- Referrals / misc user-linked rows (ignore if table missing)
DELETE FROM pending_referrals
 WHERE referrer_private_id IN (SELECT private_id FROM demo_users)
    OR referred_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM user_education
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM user_work
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM user_family_setup
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM user_birth_planets
 WHERE user_private_id IN (SELECT private_id FROM demo_users);

DELETE FROM link_requests
 WHERE from_user_private_id IN (SELECT private_id FROM demo_users)
    OR to_user_private_id IN (SELECT private_id FROM demo_users);

-- Finally remove demo users (never delete admin)
DELETE FROM users
 WHERE private_id IN (SELECT private_id FROM demo_users)
   AND private_id != 'H_U_ADMIN';

COMMIT;

-- Verify remaining accounts
SELECT private_id, first_name, last_name, account_type, is_admin
  FROM users
 ORDER BY private_id;
