#!/usr/bin/env node
/**
 * Import villages from indiaq.db (SQLite) into Supabase PostgreSQL.
 *
 * Usage:
 *   INDIAQ_DB_PATH=../indiaq.db \
 *   NEXT_PUBLIC_SUPABASE_URL=... \
 *   SUPABASE_SERVICE_ROLE_KEY=... \
 *   node scripts/import-villages.mjs [--limit 1000]
 */

import Database from "better-sqlite3";
import { createClient } from "@supabase/supabase-js";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const dbPath = process.env.INDIAQ_DB_PATH ?? resolve(__dirname, "../../indiaq.db");
const limitArg = process.argv.find((a) => a.startsWith("--limit"));
const limit = limitArg ? parseInt(limitArg.split("=")[1] ?? process.argv[process.argv.indexOf("--limit") + 1], 10) : null;

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!supabaseUrl || !serviceKey) {
  console.error("Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY");
  process.exit(1);
}

const supabase = createClient(supabaseUrl, serviceKey);
const sqlite = new Database(dbPath, { readonly: true });

function parsePath(id) {
  const parts = id.split("|").pop() ?? id;
  const segments = parts.split("/");
  const statePart = segments[1] ?? "";
  const stateCode = statePart.split(".")[0] ?? "";
  return { raw: parts, stateCode };
}

function inferNames(id, name) {
  return {
    id,
    name,
    state_name: null,
    district_name: null,
    tehsil_name: null,
    latitude: null,
    longitude: null,
  };
}

console.log(`Reading villages from ${dbPath}...`);

let query = "SELECT id, name FROM village";
if (limit) query += ` LIMIT ${limit}`;
const rows = sqlite.prepare(query).all();

console.log(`Found ${rows.length} villages. Importing in batches...`);

const BATCH = 500;
let imported = 0;

for (let i = 0; i < rows.length; i += BATCH) {
  const batch = rows.slice(i, i + BATCH).map((r) => inferNames(r.id, r.name));
  const { error } = await supabase.from("villages").upsert(batch, { onConflict: "id" });
  if (error) {
    console.error("Batch error:", error.message);
    process.exit(1);
  }
  imported += batch.length;
  console.log(`  ${imported}/${rows.length}`);
}

// Optionally enrich with state names from state table
const states = sqlite.prepare("SELECT id, name FROM state").all();
const stateMap = new Map();
for (const s of states) {
  const code = (s.id.split("|").pop() ?? s.id).split("/").pop()?.split(".")[0];
  if (code) stateMap.set(code, s.name);
}

console.log(`Enriched ${stateMap.size} state names available for future geocoding.`);
console.log("Done. Run assign coordinates separately if needed (PostGIS geom update).");

sqlite.close();
