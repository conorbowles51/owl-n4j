"""What makes up a case, computed from the database catalog.

Models alone miss 89 of the 252 tables (the phone and pattern-of-life tables are written in SQL), so the catalog of the
database being exported is the source: a table belongs to a case when it has a ``case_id`` column, or when a foreign key
chain leads to one that does. Everything else must be named below with the reason it is not part of a case: a table
nobody classified stops the export (``Unclassified``), so a new table cannot silently fall out of packages.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Held by a case or reached from one, and deliberately not carried.
LEFT_OUT = {
    "presence_sessions": "who has the case open right now; meaningless elsewhere",
    "background_tasks": "progress rows of running work",
    "evidence_upload_sessions": "uploads in transit; finished uploads are evidence files",
    "ui_problem_reports": "reports about the application, not about the case",
    "request_speed_slow": "application speed measurements",
    "case_exports": "this package's own request and earlier ones",
    "phone_exports": "generated PDF and RSMF files; drawn again from the records",
    "phone_original_bundles": "generated download of originals; built again from the evidence files",
    "phone_schema_types": "this installation's record of phone report formats, shared by every case",
    "phone_schema_fields": "this installation's record of phone report formats, shared by every case",
    "phone_schema_attributes": "this installation's record of phone report formats, shared by every case",
    "phone_schema_nesting": "this installation's record of phone report formats, shared by every case",
    "phone_schema_set_values": "this installation's record of phone report formats, shared by every case",
    "phone_schema_flags": "this installation's record of phone report formats, shared by every case",
    "phone_schema_flag_events": "this installation's record of phone report formats, shared by every case",
    "phone_schema_observations": "this installation's record of phone report formats, shared by every case",
}

# Not part of any case. Each keeps its reason so the package can state what it leaves out.
GLOBAL = {
    "alembic_version": "the schema revision, recorded in the manifest",
    "users": "people; only those a case's rows name travel, in the people part",
    "account_reset_codes": "sign-in secrets", "user_recovery_codes": "sign-in secrets", "user_two_step": "sign-in secrets",
    "login_policy": "installation setting",
    "ai_model_policies": "installation setting", "ai_provider_credentials": "installation secret",
    "ai_pricing_rates": "installation setting", "agent_prompt_versions": "installation record of prompts",
    "availability_probe": "application measurements", "host_load_minute": "application measurements",
    "request_speed_loop_lag": "application measurements", "request_speed_hourly": "application measurements",
    "request_speed_pages": "application measurements", "service_health_states": "application measurements",
    "releases": "application measurements", "system_logs": "installation log; a case's own trail is activity_events",
    "evidence_upload_registrations": "uploads in transit",
    "financial_categories": "installation list of category names; rows carry their own category name",
    "financial_category_model_cache": "installation cache", "financial_recovery_releases": "installation record",
    "geocoding_cache": "installation cache", "last_graph_states": "installation cache",
    "phone_mapping_current": "which phone mapping this installation uses",
    "phone_mapping_rows": "rows of a phone mapping; loaded with the mapping",
    "phone_reader_settings": "a person's own reader setting", "phone_user_marks": "a person's own marks",
    "pol_cell_reference": "installation reference data",
    "triage_cases": "triage workspace, not a case", "triage_hash_sets": "triage workspace, not a case",
    "triage_stages": "triage workspace, not a case", "triage_templates": "triage workspace, not a case",
    # Referenced by case rows: the rows named travel in the reference part and are added on import when missing.
    "phone_mapping_versions": "installation mappings; those a case used travel as reference rows",
    "pol_reference_dataset": "installation reference data; those a case used travel as reference rows",
    "processing_profiles": "installation profiles; those a case used travel as reference rows",
    "case_context_templates": "installation templates; those a case used travel as reference rows",
    "case_context_template_fields": "installation templates; those a case used travel as reference rows",
}

# Global tables a case's rows point at: exported as reference rows, added on import when the id is missing. In order.
REFERENCE_TABLES = ("phone_mapping_versions", "pol_reference_dataset", "processing_profiles",
                    "case_context_templates", "case_context_template_fields")

# Private to the person who owns them: the app answers only that person, so a case owner's export carries only their
# own. A super admin's export is the operator's whole copy and carries all of them. Children follow by foreign key.
OWNER_PRIVATE = {"chat_conversations": "owner_user_id", "agent_threads": "owner_user_id"}

# Carried in the package as a record of who had access, never loaded: access to the new case is given by its owner.
RECORD_ONLY = ("case_memberships",)

# Integer ids from a sequence, and the columns (without a foreign key) that hold them: moved by one offset on import, so
# they stay unique beside the rows already there and every reference still holds.
SEQUENCE_REFERENCES = {
    "pol_place_observation": ("id", (("pol_colocation_item", "a_observation_id"),
                                     ("pol_colocation_item", "b_observation_id"))),
    "pol_wifi_anchor": ("id", (("pol_place_observation", "wifi_anchor_id"),)),
    "phone_reading_changes": ("seq", (("phone_link_choices", "through_seq"),)),
}

# uuid columns holding an installation's own derived value, kept as they are.
KEEP_UUID_COLUMNS = frozenset({"mapping_version_id", "meaning_mapping_version_id", "activity_mapping_version",
                               "mapping_set_id", "engine_job_id"})


class Unclassified(Exception):
    """The database has a table this code does not know the place of."""


@dataclass
class Table:
    name: str
    columns: list = field(default_factory=list)      # names, in order
    types: dict = field(default_factory=dict)        # name -> format_type
    generated: set = field(default_factory=set)
    required: set = field(default_factory=set)       # NOT NULL with no default
    primary_key: list = field(default_factory=list)
    foreign_keys: list = field(default_factory=list)  # (columns, target table, target columns, on delete)
    sequence_column: str | None = None               # single integer key filled from a sequence
    sequence_name: str | None = None
    has_case_id: bool = False


@dataclass
class Inventory:
    tables: dict
    case_tables: list      # dependency order is not needed: loading runs with checks deferred to the end
    children: dict         # table with no case_id -> the foreign key leading to the case
    left_out: dict
    global_tables: dict

    def part_names(self):
        return list(self.case_tables)


def read_catalog(conn) -> dict:
    """Every ordinary table of the public schema with its columns, keys and foreign keys."""
    tables: dict = {}
    cur = conn.execute(
        "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.atthasdef, a.attgenerated, "
        "a.attidentity, pg_get_expr(d.adbin, d.adrelid) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
        "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition AND a.attnum > 0 "
        "AND NOT a.attisdropped ORDER BY c.relname, a.attnum")
    sequences = {}
    for t, col, typ, not_null, has_default, generated, identity, default in cur:
        table = tables.setdefault(t, Table(t))
        table.columns.append(col)
        table.types[col] = typ
        if generated:
            table.generated.add(col)
        if not_null and not has_default and not identity and not generated:
            table.required.add(col)
        if col == "case_id":
            table.has_case_id = True
        if default and default.startswith("nextval(") or identity:
            sequences[(t, col)] = default
    for t, cols in conn.execute(
            "SELECT c.relname, array_agg(a.attname ORDER BY k.ord) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum, ord) "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum "
            "WHERE i.indisprimary AND n.nspname = 'public' GROUP BY c.relname"):
        if t in tables:
            tables[t].primary_key = list(cols)
    for t, cols, target, target_cols, action in conn.execute(
            "SELECT c.relname, (SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.conkey) WITH ORDINALITY k(n, ord) "
            "JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n), f.relname, "
            "(SELECT array_agg(a.attname ORDER BY k.ord) FROM unnest(con.confkey) WITH ORDINALITY k(n, ord) "
            "JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n), con.confdeltype "
            "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid JOIN pg_class f ON f.oid = con.confrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE con.contype = 'f' AND n.nspname = 'public' "
            "ORDER BY c.relname, con.conname"):
        if t in tables:
            tables[t].foreign_keys.append((list(cols), target, list(target_cols), action))
    for (t, col), default in sequences.items():
        table = tables[t]
        if table.primary_key == [col] and table.types[col] in ("bigint", "integer"):
            table.sequence_column = col
            table.sequence_name = pg_sequence(conn, t, col)
    return tables


def pg_sequence(conn, table, column):
    return conn.execute("SELECT pg_get_serial_sequence(%s, %s)", (table, column)).fetchone()[0]


def classify(tables: dict) -> Inventory:
    """Sort every table into the case, left out or global. Raises Unclassified naming any table that fits none."""
    left_out = {t: why for t, why in LEFT_OUT.items() if t in tables}
    in_case = {t for t, table in tables.items() if table.has_case_id and t not in left_out}
    children: dict = {}
    changed = True
    while changed:
        changed = False
        for name, table in tables.items():
            if name in in_case or name in left_out or name in GLOBAL or name == "cases":
                continue
            for fk in table.foreign_keys:
                if fk[1] in in_case:
                    children[name] = fk
                    in_case.add(name)
                    changed = True
                    break
    known = in_case | set(left_out) | set(GLOBAL) | {"cases"}
    unknown = sorted(set(tables) - known)
    if unknown:
        raise Unclassified("These tables are not classified as part of a case or not: " + ", ".join(unknown))
    return Inventory(tables=tables, case_tables=sorted(in_case), children=children, left_out=left_out,
                     global_tables={t: GLOBAL[t] for t in sorted(GLOBAL) if t in tables})


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def scope_where(inv: Inventory, table: str, alias: str, *, private_for: str | None = None, _seen=()) -> str:
    """The condition selecting ``table``'s rows of the case (bound as %(case)s).

    ``private_for`` is a user id: rows private to anyone else are left out, with everything that cannot exist without
    them (a required foreign key to such a row)."""
    t = inv.tables[table]
    conds = []
    if t.has_case_id:
        conds.append(f"{alias}.case_id = %(case)s")
    else:
        fk = inv.children[table]
        conds.append(_in_parent(inv, alias, fk, private_for, _seen + (table,)))
    if private_for is not None:
        owner = OWNER_PRIVATE.get(table)
        if owner:
            conds.append(f"{alias}.{_quote(owner)} = %(me)s")
        elif t.has_case_id:
            for fk in private_required_fks(inv, table):
                conds.append(f"({alias}.{_quote(fk[0][0])} IS NULL OR "
                             + _in_parent(inv, alias, fk, private_for, _seen + (table,)) + ")")
    return " AND ".join(conds)


def _in_parent(inv, alias, fk, private_for, seen) -> str:
    cols, target, target_cols, _ = fk
    inner = "p" + str(len(seen))
    where = scope_where(inv, target, inner, private_for=private_for, _seen=seen)
    left = ", ".join(f"{alias}.{_quote(c)}" for c in cols)
    right = ", ".join(f"{inner}.{_quote(c)}" for c in target_cols)
    return f"({left}) IN (SELECT {right} FROM {_quote(target)} {inner} WHERE {where})"


def _reaches_private(inv, table, seen=()) -> bool:
    if table in OWNER_PRIVATE:
        return True
    t = inv.tables.get(table)
    if t is None or table in seen:
        return False
    return any(fk[1] in inv.case_tables and _reaches_private(inv, fk[1], seen + (table,)) for fk in t.foreign_keys)


def private_required_fks(inv, table) -> list:
    """Foreign keys of ``table`` that lead to private rows and cannot be emptied (NOT NULL): the row goes with them."""
    t = inv.tables[table]
    return [fk for fk in t.foreign_keys if fk[1] != table and fk[1] in inv.case_tables
            and all(c in t.required for c in fk[0]) and _reaches_private(inv, fk[1])]


def private_optional_fks(inv, table) -> list:
    """Foreign keys of ``table`` leading to private rows that can be emptied: the row stays with the link blanked."""
    t = inv.tables[table]
    required = private_required_fks(inv, table)
    return [fk for fk in t.foreign_keys if fk[1] != table and fk[1] in inv.case_tables and fk not in required
            and len(fk[0]) == 1 and _reaches_private(inv, fk[1])]


def select_rows(inv: Inventory, table: str, *, private_for: str | None = None) -> str:
    """One JSON text per row. Numbers keep their exact digits (row_to_json writes the stored value)."""
    alias = "t"
    where = scope_where(inv, table, alias, private_for=private_for)
    order = ", ".join(f"{alias}.{_quote(c)}" for c in inv.tables[table].primary_key) or "1"
    expr = f"row_to_json({alias})::text"
    if private_for is not None:
        blanks = private_optional_fks(inv, table)
        if blanks:
            sets = ", ".join(
                f"'{fk[0][0]}', CASE WHEN " + _in_parent(inv, alias, fk, private_for, (table,)) +
                f" THEN {alias}.{_quote(fk[0][0])} ELSE NULL END" for fk in blanks)
            expr = f"(to_jsonb({alias}) || jsonb_build_object({sets}))::text"
    return f"SELECT {expr} FROM {_quote(table)} {alias} WHERE {where} ORDER BY {order}"
