"""Regenerate regkg-taxonomy.md from regkg.ttl (the TTL is the source of truth).
Usage: python3 generate_taxonomy.py   (requires rdflib)"""

from rdflib import OWL, RDF, RDFS, Graph, Namespace
from rdflib.namespace import SKOS

g = Graph().parse("regkg.ttl")
RK = Namespace("https://example.org/regkg#")
NS = [
    ("rk:", str(RK)),
    ("skos:", str(SKOS)),
    ("prov:", "http://www.w3.org/ns/prov#"),
    ("eli:", "http://data.europa.eu/eli/ontology#"),
    ("xsd:", "http://www.w3.org/2001/XMLSchema#"),
]


def short(u):
    s = str(u)
    for p, ns in NS:
        if s.startswith(ns):
            return p + s[len(ns) :]
    return s


def label(u):
    ls = {
        label_literal.language: str(label_literal)
        for label_literal in list(g.objects(u, RDFS.label)) + list(g.objects(u, SKOS.prefLabel))
    }
    return ls.get("en") or ls.get("fr") or next(iter(ls.values()), "")


def comment(u):
    cs = {c.language: str(c) for c in g.objects(u, RDFS.comment)}
    return (cs.get("en") or cs.get("fr") or "").replace("\n", " ").replace("|", "/")


classes = sorted(
    {c for c in g.subjects(RDF.type, OWL.Class) if str(c).startswith(str(RK))}, key=short
)
children, roots = {}, []
for c in classes:
    parents = [p for p in g.objects(c, RDFS.subClassOf) if p in classes]
    if parents:
        for p in parents:
            children.setdefault(p, []).append(c)
    else:
        roots.append(c)

out = [
    "# RegKG ontology v0.2 — taxonomy reference",
    "",
    "> Generated from `regkg.ttl` (source of truth) by `generate_taxonomy.py`. Do not edit by hand.",
    "",
    "Layers: L1 Document · L2 Normative · L3 Domain · L4 Pivot · L5 Relations · L6 Provenance · "
    "L7 Applicability · L8 Assessment (private).",
    "",
    "## 1. Class hierarchy",
    "",
    "`[Label]` = Neo4j node label in the shared knowledge graph; `(private)` = private store only.",
    "",
    "```",
]


def walk(c, depth):
    lp, st = g.value(c, RK.lpgLabel), g.value(c, RK.storage)
    ext = [p for p in g.objects(c, RDFS.subClassOf) if p not in classes]
    tag = (
        (f"  [{lp}]" if lp else "")
        + ("  (private)" if str(st or "") == "private" else "")
        + (f"  ⊑ {', '.join(short(e) for e in ext)}" if ext else "")
    )
    out.append("    " * depth + ("└─ " if depth else "") + f"{short(c)} — {label(c)}{tag}")
    for k in sorted(children.get(c, []), key=short):
        walk(k, depth + 1)


for r in roots:
    walk(r, 0)
out += ["```", "", "## 2. Controlled vocabularies (SKOS concept schemes)", ""]
schemes = sorted(
    set(g.subjects(RDF.type, SKOS.ConceptScheme))
    | set(g.subjects(RDF.type, RK.ClassificationScheme)),
    key=short,
)
for sc in schemes:
    concepts = sorted(
        g.subjects(SKOS.inScheme, sc),
        key=lambda x: (str(g.value(x, SKOS.notation) or ""), short(x)),
    )
    out += [f"### {label(sc) or short(sc)} (`{short(sc)}`)", ""]
    if not concepts:
        out += ["*Populated per document (A-Box).*", ""]
        continue
    out += ["| Concept | Label | Note |", "|---|---|---|"]
    for c in concepts:
        note = str(
            g.value(c, SKOS.scopeNote)
            or g.value(c, SKOS.definition)
            or g.value(c, SKOS.example)
            or ""
        ).replace("|", "/")
        out.append(f"| `{short(c)}` | {label(c)} | {note} |")
    out.append("")


def props(kind, title):
    ps = sorted({p for p in g.subjects(RDF.type, kind) if str(p).startswith(str(RK))}, key=short)
    rows = [
        f"## {title}",
        "",
        "| Property | Domain | Range | Neo4j | Comment |",
        "|---|---|---|---|---|",
    ]
    for p in ps:
        d = ", ".join(short(x) for x in g.objects(p, RDFS.domain)) or "—"
        r = ", ".join(short(x) for x in g.objects(p, RDFS.range)) or "—"
        rel = g.value(p, RK.lpgRelationship)
        rows.append(
            f"| `{short(p)}` | {d} | {r} | {('`' + str(rel) + '`') if rel else ''} | {comment(p)[:160]} |"
        )
    return rows + [""]


out += props(OWL.ObjectProperty, "3. Object properties (relationships)")
out += props(OWL.DatatypeProperty, "4. Datatype properties (node properties)")
ext_rels = sorted(
    (short(s), str(o))
    for s, o in g.subject_objects(RK.lpgRelationship)
    if not str(s).startswith(str(RK))
)
out += (
    ["## 5. Relationships from reused vocabularies", "", "| Property | Neo4j |", "|---|---|"]
    + [f"| `{a}` | `{b}` |" for a, b in ext_rels]
    + [""]
)
open("regkg-taxonomy.md", "w").write("\n".join(out))
print(f"{len(classes)} classes, {len(schemes)} schemes -> regkg-taxonomy.md")
