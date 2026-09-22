# Future Databricks adapter

No Databricks runtime implementation or platform comparison is claimed in Lab v1.

| Portable artifact/capability | Snowflake | Databricks replacement |
|---|---|---|
| Frozen data/PKs | Benchmark tables | Unity Catalog Delta tables |
| Business definitions | Semantic Views | Reviewed SQL views plus Genie/tool metadata |
| Analytical agent tool | Cortex Analyst | Genie-backed analytical tool |
| Orchestration | Cortex Agents | Configured agent or Genie agent API |
| Deployment identity | VERSION$N plus dependency hashes | Frozen artifact/config and deployment ID |
| Evaluation | Portable core plus native diagnostics | Same core wrapped in MLflow code scorers |
| Evidence | Raw response and observability events | Raw response and MLflow spans/traces |
| Accounting | Credits plus warehouse usage | Tokens/serving usage, DBUs and SQL compute |
| Release | Alias routing with decision record | Deployment routing with same decision record |

Implement PlatformAdapter with the same invocation/result contracts. The wrapper
around `mlflow.genai.evaluate()` must call the portable comparator; do not substitute
a native correctness scorer with different semantics. Native judges remain separately
versioned supplementary metrics. Preserve requested/observed models and routing limits.

First validate data and oracle parity, then invocation/trace normalization, then
cost attribution. An exposed benchmark replay demonstrates reuse and engineering
differences. It cannot measure unseen accuracy after public answers are available.

Do not assume one-to-one mapping of semantic metadata, deployment aliases, sampling
controls or models. Record every irreducible capability difference in the manifest.

Later acceptance: the same fixture/contract tests pass; SQL results match the frozen
oracle; MLflow assessments link to original invocation IDs; original split assignment
and policy hashes remain unchanged. A new prospective comparison needs fresh hidden
questions and a separate protocol, not a platform-superiority claim.
