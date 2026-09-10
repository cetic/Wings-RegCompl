"""Set all SmartAir verification actions to Verified."""

"""check smartair"""
import uuid
from database import SessionLocal
import models
from neo4j import GraphDatabase

db = SessionLocal()
smartair_id = "cb52d4c8-4ce1-4aaa-b0f6-bbcfdb2ed9c0"
a = (
    db.query(models.ProductAssessment)
    .filter(models.ProductAssessment.id == smartair_id)
    .first()
)
obligs = a.obligation_ids
print(f"SmartAir has {len(obligs)} obligations")

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
with driver.session() as s:
    result = s.run(
        "MATCH (o:Obligation)-[:HAS_VERIFICATION]->(v:VerificationAction) "
        "WHERE o.id IN $obl_ids RETURN DISTINCT v.id AS vid",
        obl_ids=obligs,
    )
    vids = [r["vid"] for r in result]
    print(f"Total verifications: {len(vids)}")

existing = (
    db.query(models.VerificationAnswer)
    .filter(models.VerificationAnswer.assessment_id == smartair_id)
    .all()
)
existing_vids = {ans.verification_id for ans in existing}
print(f"Already answered: {len(existing_vids)}")

new_count = 0
for vid in vids:
    if vid not in existing_vids:
        ans = models.VerificationAnswer(
            id=str(uuid.uuid4()),
            assessment_id=smartair_id,
            verification_id=vid,
            status="Verified",
            evidence="",
            notes="",
        )
        db.add(ans)
        new_count += 1
        existing_vids.add(vid)

updated = 0
for ans in existing:
    if ans.status != "Verified":
        ans.status = "Verified"
        updated += 1

db.commit()
print(f"Created {new_count} new, updated {updated} existing. All set to Verified.")
db.close()
driver.close()
