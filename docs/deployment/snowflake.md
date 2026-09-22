# Snowflake deployment notes

This document supplements the [reproduction guide](../reproduction.md). It describes the adapter's intended role boundaries and local SQL generation. It is not a turnkey rerun of the completed TASK-0019 experiment. Snowflake interfaces, grants, model availability, and billing behavior can change; confirm current requirements in Snowflake documentation and in your account before deployment.

## Credentials and profiles

Install the optional connector with `python -m pip install -e ".[snowflake]"`. The adapter connects by a named connector profile, supplied with `--profile`. Keep `connections.toml` and any private key in the connector's user-level configuration location outside the repository. Prefer SSO/browser or an approved key-pair method. The example profile contains no live account values.

## Role boundaries

The SQL in `platforms/snowflake/sql/001_bootstrap.sql` creates deployment, runtime, evaluator, and native-diagnostics roles; creates the lab database/schemas and an initially suspended XSMALL warehouse; and grants Cortex Agent and Cortex Analyst user roles to the runtime role. The warehouse auto-suspends after five minutes to allow normal agent planning and tool execution to finish. A longer active window can increase compute cost.

An account administrator or appropriately privileged deployment role must create the base resources and grants. The developer role creates semantic views and agents. The runtime role receives access to the required tables, semantic view, named agent, and warehouse. The evaluator role's private schema is separate and must never be granted to the runtime identity. Assign the required default role and default warehouse to the user that calls the agent; Snowflake's Cortex Agent permission checks use the caller's default role.

The bootstrap script is a starting point, not a least-privilege proof for a particular account. Review every role grant, inherited grant, secondary role, object owner, network policy, and account-level Cortex/model setting. Do not grant `ACCOUNTADMIN` to a runtime identity.

## Render and deploy

`python -m evaluation.cli render-snowflake ...` verifies a release and writes SQL/JSON under a fresh local output directory. It never connects or executes SQL. The renderer currently emits the generic A0–A2 synthetic/reference configuration. Review the generated files, confirm database/schema/model/warehouse names, and execute only approved statements through your Snowflake deployment process.

Create or load authorized tables, build the matching semantic view, create a named agent version, apply explicit grants, and verify the version and tool access under the intended runtime role. The renderer's output does not guarantee that a particular account accepts the DDL or supports the selected model.

## Costs and evidence

Resuming a warehouse, executing queries, running agent tools, and calling Cortex can incur usage. Agent orchestration and downstream tool calls can be billed separately. Use current account pricing and rate-card information; do not copy historical cost estimates into a new budget. Perform a fresh conservative preflight, include warehouse and uncertainty allowances, and stop when metering or attribution is unresolved.

Invocation exceptions can leave submission status ambiguous. Do not retry an ambiguous request for quality. Preserve its denominator status and reconcile provider usage before finalizing costs. `verify-run`, scoring, and report generation operate on saved local evidence and do not contact Snowflake.

An earlier smoke check against a Snowflake trial used only the public synthetic fixture. After the warehouse auto-suspend window was increased to five minutes, a single A0 call completed through Cortex Analyst, SQL execution, and the agent response. This established one live path at that time; it did not validate the private research data or make usage attribution complete. It is not a promise of current account behavior.

## Snowflake references

- [Cortex Agent access control and authentication](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-setup)
- [Cortex Analyst access control](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- [Cortex Agent overview, availability, and cost](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Python connector connection profiles](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect)
