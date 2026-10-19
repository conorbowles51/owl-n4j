# Financial identity graph validation

The investigator journey remains saved payments and reviewed account identities → case graph → linked investigation. A background identity projection timeout can leave that graph behind the saved Financial records. Ledger admission and graph completion must be reported separately.

Target validation previously performed an unlabelled optional match for each requested key, separately for external entities, accounts and parties. A local Neo4j profile with 300 synthetic keys measured 8,100 database hits for the old query and 27 for one case-scoped pass. These measurements demonstrate repeated scanning in the query, not a production latency estimate or proof that it is the sole cause of the observed timeout.

Validation now retrieves matching keys and labels in one pass. It preserves every match: missing or ambiguous external targets, duplicate financial keys and collisions with ordinary entities still stop projection. New financial nodes may still be created when their keys have no matches. Empty plans do not query the graph. The graph mutex, SQL snapshot boundary, revision checks, timeout and investigator-owned names, notes and relationships are unchanged.

Verification: ten focused validation/lock-boundary tests and five real Neo4j integration tests passed against the isolated local synthetic database. Integration covers case isolation, cross-label collisions, duplicate targets, concurrent revisions, idempotent retries, retained notes and manual links, and pending payment projections. Live deployment and recovery of the reported timeout remain unverified; no production graph or service was changed during this diagnosis.
