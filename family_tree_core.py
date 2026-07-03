"""Enhanced family tree schema — graph nodes, trees, connection requests."""

from __future__ import annotations

import sqlite3

FAMILY_TREES_DDL = """
CREATE TABLE IF NOT EXISTS family_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    root_node_id INTEGER,
    owner_private_id TEXT NOT NULL,
    tree_name TEXT DEFAULT 'My Family Tree',
    privacy_level TEXT DEFAULT 'family' CHECK(privacy_level IN ('private', 'family', 'public')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

FAMILY_TREE_NODES_DDL = """
CREATE TABLE IF NOT EXISTS family_tree_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_id INTEGER NOT NULL,
    linked_user_private_id TEXT,
    display_name TEXT NOT NULL,
    gender TEXT CHECK(gender IN ('M', 'F', 'O')),
    date_of_birth DATE,
    date_of_death DATE,
    is_deceased INTEGER DEFAULT 0,
    birth_location TEXT,
    current_location TEXT,
    bio TEXT,
    profile_photo_url TEXT,
    generation_level INTEGER DEFAULT 0,
    x_position REAL,
    y_position REAL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

FAMILY_TREE_RELATIONSHIPS_DDL = """
CREATE TABLE IF NOT EXISTS family_tree_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tree_id INTEGER NOT NULL,
    from_node_id INTEGER NOT NULL,
    to_node_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL CHECK(relationship_type IN (
        'parent', 'child', 'spouse', 'sibling', 'grandparent', 'grandchild',
        'uncle_aunt', 'niece_nephew', 'cousin', 'step_parent', 'step_child',
        'adoptive_parent', 'adoptive_child', 'half_sibling'
    )),
    is_primary INTEGER DEFAULT 1,
    start_date DATE,
    end_date DATE,
    notes TEXT,
    UNIQUE(tree_id, from_node_id, to_node_id, relationship_type)
);
"""

FAMILY_CONNECTION_REQUESTS_DDL = """
CREATE TABLE IF NOT EXISTS family_connection_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_tree_id INTEGER NOT NULL,
    from_node_id INTEGER NOT NULL,
    to_tree_id INTEGER NOT NULL,
    to_node_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'rejected')),
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def migrate_family_tree_enhanced_schema(conn: sqlite3.Connection) -> None:
    """Create enhanced family tree tables (no FK — avoids users.private_id mismatch)."""
    conn.executescript(FAMILY_TREES_DDL)
    conn.executescript(FAMILY_TREE_NODES_DDL)
    conn.executescript(FAMILY_TREE_RELATIONSHIPS_DDL)
    conn.executescript(FAMILY_CONNECTION_REQUESTS_DDL)
    conn.commit()


AGE_CATEGORY_MID: dict[str, int] = {
    "Balak": 12,
    "Yuvak": 35,
    "Vridh": 60,
    "Sanyas": 80,
}

ALLOWED_GENDERS = {"M", "F", "O", "Male", "Female", "Other"}
ALLOWED_STATUSES = {"unmarried", "married", "single-parent", "widowed"}


def _norm_gender(value: str) -> str:
    g = (value or "").strip()
    if g in {"M", "Male", "male"}:
        return "Male"
    if g in {"F", "Female", "female"}:
        return "Female"
    if g in {"O", "Other", "other"}:
        return "Other"
    return g


def _age_from_category(category: str) -> tuple[int | None, str]:
    cat = (category or "").strip()
    if cat in AGE_CATEGORY_MID:
        return AGE_CATEGORY_MID[cat], cat
    return None, cat


def validate_public_id(conn: sqlite3.Connection, public_id: str) -> str:
    pid = (public_id or "").strip()
    if not pid:
        return ""
    row = conn.execute(
        "SELECT public_id FROM users WHERE public_id = ? COLLATE NOCASE",
        (pid,),
    ).fetchone()
    if not row:
        raise ValueError(f"Public ID not found: {pid}")
    return str(row["public_id"] or "").strip()


def upsert_tree_name(conn: sqlite3.Connection, owner_private_id: str, tree_name: str) -> None:
    name = (tree_name or "").strip() or "My Family Tree"
    row = conn.execute(
        "SELECT id FROM family_trees WHERE owner_private_id = ?",
        (owner_private_id,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE family_trees SET tree_name = ? WHERE owner_private_id = ?",
            (name, owner_private_id),
        )
    else:
        conn.execute(
            "INSERT INTO family_trees (owner_private_id, tree_name) VALUES (?, ?)",
            (owner_private_id, name),
        )


def _graph_insert_edge(
    conn: sqlite3.Connection, src: int, tgt: int, rel_type: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO family_relationships (source_id, target_id, relation_type)
        VALUES (?, ?, ?)
        """,
        (src, tgt, rel_type),
    )


def _graph_apply_pair(
    conn: sqlite3.Connection, m1: int, m2: int, relationship_type: str
) -> None:
    rt = relationship_type.strip().lower()
    if rt == "parent":
        _graph_insert_edge(conn, m1, m2, "parent")
        _graph_insert_edge(conn, m2, m1, "child")
    elif rt == "child":
        _graph_insert_edge(conn, m1, m2, "child")
        _graph_insert_edge(conn, m2, m1, "parent")
    elif rt == "spouse":
        _graph_insert_edge(conn, m1, m2, "spouse")
        _graph_insert_edge(conn, m2, m1, "spouse")
    elif rt == "sibling":
        _graph_insert_edge(conn, m1, m2, "sibling")
        _graph_insert_edge(conn, m2, m1, "sibling")


def _wipe_family_graph(conn: sqlite3.Connection, user_pid: str) -> None:
    cur = conn.execute(
        "SELECT id FROM family_members WHERE user_private_id = ? AND source != 'self'",
        (user_pid,),
    )
    for row in cur.fetchall():
        mid = int(row["id"])
        conn.execute(
            "DELETE FROM family_relationships WHERE source_id = ? OR target_id = ?",
            (mid, mid),
        )
    conn.execute(
        "DELETE FROM family_members WHERE user_private_id = ? AND source != 'self'",
        (user_pid,),
    )


def _insert_member(
    conn: sqlite3.Connection,
    user_pid: str,
    *,
    name: str,
    relationship: str,
    gender: str = "",
    age_category: str = "",
    public_id: str = "",
    is_dead: bool = False,
) -> int:
    member_name = (name or "").strip()
    if not member_name:
        raise ValueError(f"Name is required for {relationship}")
    g = _norm_gender(gender)
    if is_dead and not (age_category or "").strip():
        age, modifier = None, ""
    else:
        age, modifier = _age_from_category(age_category)
    linked = validate_public_id(conn, public_id) if public_id else ""
    is_ph = 0 if member_name and member_name.lower() not in {"add", "unknown"} else 1
    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, is_placeholder, account_public_id, source,
            parent_link
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'form', NULL)
        """,
        (
            user_pid,
            member_name,
            relationship,
            g,
            age,
            modifier,
            1 if is_dead else 0,
            is_ph,
            linked or None,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _person_block(payload: dict, *, required: bool = False) -> dict | None:
    if not payload or not isinstance(payload, dict):
        if required:
            raise ValueError("Required person block missing")
        return None
    if payload.get("skip"):
        return None
    name = str(payload.get("name") or "").strip()
    if not name:
        if required:
            raise ValueError("Name is required")
        return None
    gender = str(payload.get("gender") or "").strip()
    age_category = str(payload.get("age_category") or payload.get("age_group") or "").strip()
    is_dead = bool(payload.get("is_deceased") or payload.get("is_dead"))
    if not gender:
        raise ValueError(f"Gender is required for {name}")
    if not is_dead and not age_category:
        raise ValueError(f"Age category is required for {name}")
    return {
        "name": name,
        "gender": gender,
        "age_category": age_category,
        "public_id": str(payload.get("public_id") or "").strip(),
        "is_dead": is_dead,
    }


def process_family_setup(
    conn: sqlite3.Connection,
    user_pid: str,
    self_id: int,
    payload: dict,
) -> dict:
    """Build family graph from wizard payload. Caller must commit."""
    rs = str(payload.get("relationship_status") or "").strip().lower().replace("_", "-")
    if rs == "single_parent":
        rs = "single-parent"
    if rs not in ALLOWED_STATUSES:
        raise ValueError("relationship_status is required")

    tree_name = str(payload.get("tree_name") or "").strip()
    upsert_tree_name(conn, user_pid, tree_name)

    _wipe_family_graph(conn, user_pid)

    father = _person_block(payload.get("father") or {})
    mother = _person_block(payload.get("mother") or {})
    father_id = mother_id = None
    if father:
        father_id = _insert_member(
            conn, user_pid, name=father["name"], relationship="Father",
            gender=father["gender"], age_category=father["age_category"],
            public_id=father["public_id"], is_dead=father["is_dead"],
        )
        _graph_apply_pair(conn, father_id, self_id, "parent")
    if mother:
        mother_id = _insert_member(
            conn, user_pid, name=mother["name"], relationship="Mother",
            gender=mother["gender"], age_category=mother["age_category"],
            public_id=mother["public_id"], is_dead=mother["is_dead"],
        )
        _graph_apply_pair(conn, mother_id, self_id, "parent")
    if father_id and mother_id:
        _graph_apply_pair(conn, father_id, mother_id, "spouse")

    spouse_block = None
    if rs in {"married", "widowed"}:
        spouse_block = _person_block(payload.get("spouse") or {}, required=True)
    if spouse_block:
        spouse_id = _insert_member(
            conn, user_pid, name=spouse_block["name"], relationship="Spouse",
            gender=spouse_block["gender"], age_category=spouse_block["age_category"],
            public_id=spouse_block["public_id"],
            is_dead=spouse_block["is_dead"] or rs == "widowed",
        )
        _graph_apply_pair(conn, spouse_id, self_id, "spouse")

    children = payload.get("children") or []
    if rs == "single-parent" and not children:
        raise ValueError("At least one child is required for single parent status")
    if isinstance(children, list):
        for ch in children:
            block = _person_block(ch, required=True)
            if not block:
                continue
            cid = _insert_member(
                conn, user_pid, name=block["name"], relationship="Child",
                gender=block["gender"], age_category=block["age_category"],
                public_id=block["public_id"], is_dead=block["is_dead"],
            )
            _graph_apply_pair(conn, self_id, cid, "parent")

    siblings = payload.get("siblings") or []
    if isinstance(siblings, list):
        for sib in siblings:
            block = _person_block(sib, required=True)
            if not block:
                continue
            rel = str(sib.get("relation") or "Sibling").strip() or "Sibling"
            sid = _insert_member(
                conn, user_pid, name=block["name"], relationship=rel,
                gender=block["gender"], age_category=block["age_category"],
                public_id=block["public_id"], is_dead=block["is_dead"],
            )
            _graph_apply_pair(conn, sid, self_id, "sibling")

    gp = payload.get("grandparents") or {}
    if isinstance(gp, dict):
        gp_map = {
            "paternal_grandfather": ("Paternal Grandfather", father_id),
            "paternal_grandmother": ("Paternal Grandmother", father_id),
            "maternal_grandfather": ("Maternal Grandfather", mother_id),
            "maternal_grandmother": ("Maternal Grandmother", mother_id),
        }
        gp_ids: dict[str, int] = {}
        for key, (rel_label, parent_id) in gp_map.items():
            block = _person_block(gp.get(key) or {})
            if not block or not parent_id:
                continue
            gid = _insert_member(
                conn, user_pid, name=block["name"], relationship=rel_label,
                gender=block["gender"], age_category=block["age_category"],
                public_id=block["public_id"], is_dead=block["is_dead"],
            )
            _graph_apply_pair(conn, gid, parent_id, "parent")
            gp_ids[key] = gid
        if "paternal_grandfather" in gp_ids and "paternal_grandmother" in gp_ids:
            _graph_apply_pair(conn, gp_ids["paternal_grandfather"], gp_ids["paternal_grandmother"], "spouse")
        if "maternal_grandfather" in gp_ids and "maternal_grandmother" in gp_ids:
            _graph_apply_pair(conn, gp_ids["maternal_grandfather"], gp_ids["maternal_grandmother"], "spouse")

    return {"relationship_status": rs, "tree_name": tree_name or "My Family Tree"}

