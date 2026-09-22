"""Small command-line interface; default commands are local and cost-free."""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from evaluation.artifacts import digest, load_json, write_once
from evaluation.contracts import GroundTruth, Question, Split
from evaluation.costs import Budget, Quote
from evaluation.demo import run_demo
from evaluation.oracle import verify_release
from evaluation.runner import run_batch, schedule
from evaluation.scoring import assess, summarize
from evaluation.sealing import Campaign, open_payload, seal_payload


def _render(args: argparse.Namespace) -> dict[str, Any]:
    from platforms.snowflake.deployment import create_agent_sql, literal, render_bundle

    verify_release(args.release, allow_synthetic=args.allow_synthetic)
    bundle = render_bundle(
        args.database,
        args.schema,
        load_json(args.release / "data.json"),
        args.model,
        args.a2_parent,
        args.warehouse,
    )
    args.output.mkdir(parents=True, exist_ok=False)
    write_once(args.output / "bundle.json", bundle)
    for name, statements in [
        ("010_tables.sql", bundle["tables"]),
        ("020_semantics.sql", bundle["semantic_views"]),
    ]:
        (args.output / name).write_text("\n\n".join(statements) + "\n", encoding="utf-8")
    agent = f"{args.database}.AGENTS.BENCHMARK_AGENT"
    for index, candidate in enumerate(["A0", "A1", "A2"]):
        spec = bundle["candidates"][candidate]["spec"]
        if candidate == "A0":
            statements = [create_agent_sql(agent, spec)]
        else:
            statements = []
            if candidate == "A2":
                statements.append(f"ALTER AGENT {agent} ADD LIVE VERSION FROM LAST;")
            statements.extend(
                [
                    f"ALTER AGENT {agent} MODIFY LIVE VERSION SET SPECIFICATION = "
                    + literal(json.dumps(spec, ensure_ascii=False))
                    + ";",
                    f"ALTER AGENT {agent} COMMIT;",
                ]
            )
        statements.append(f"SHOW VERSIONS IN AGENT {agent};")
        (args.output / f"03{index}_{candidate}.sql").write_text(
            "-- Run this stage only after recording the previous TRAIN decision.\n"
            + "\n\n".join(statements)
            + "\n",
            encoding="utf-8",
        )
    grants = [
        f"GRANT SELECT ON TABLE {args.database}.{args.schema}.{table.upper()} TO ROLE {role};"
        for table in load_json(args.release / "data.json")
        for role in ["LAB_RUNTIME", "LAB_DEVELOPER"]
    ]
    views = {v["semantic_view"] for v in bundle["candidates"].values()}
    grants += [
        f"GRANT SELECT ON SEMANTIC VIEW {view} TO ROLE LAB_RUNTIME;" for view in sorted(views)
    ]
    grants.append(f"GRANT USAGE ON AGENT {agent} TO ROLE LAB_RUNTIME;")
    (args.output / "040_grants.sql").write_text("\n".join(grants) + "\n", encoding="utf-8")
    return {"output": str(args.output), "executed": False, "bundle_sha256": digest(bundle)}


def _run_snowflake(args: argparse.Namespace) -> dict[str, Any]:
    from platforms.snowflake.adapter import SnowflakeAdapter, connect

    config = load_json(args.config)
    if config.get("template_only"):
        raise ValueError("Fill and review the batch template before invoking Snowflake")
    campaign = Campaign(Path(config["campaign"]))
    split = Split(config["split"])
    campaign.authorize(split, "execute")
    if split == Split.TRAIN:
        questions = [Question.from_dict(row) for row in load_json(Path(config["questions"]))]
        if any(q.split != Split.TRAIN for q in questions):
            raise ValueError("TRAIN file contains hidden questions")
        protocol = load_json(campaign.root / "protocol.json")
        if protocol.get("classification") == "prospective_procedurally_sealed":
            if digest(load_json(Path(config["questions"]))) != protocol["train_questions_sha256"]:
                raise ValueError("TRAIN questions differ from the frozen protocol")
    else:
        expected_hash = load_json(campaign.root / "protocol.json")["sealed_payloads"][split.value]
        payload = open_payload(
            Path(config["sealed_payload"]),
            Path(config["key_file"]),
            campaign,
            split,
            "execute",
            "solo_evaluator",
            expected_hash,
        )
        questions = [Question.from_dict(row) for row in payload["questions"]]
    deployments = load_json(Path(config["deployments"]))
    plan = (
        load_json(campaign.root / "test_schedule.json")
        if split == Split.TEST
        else schedule(questions, list(deployments), 20260919)
    )
    # ADR-0003 -> ADR-0006 -> ADR-0007 amended the Benchmark R1 ceiling to a hard USD 30. Budget
    # itself still refuses anything above USD 30 or a reserve below USD 2.
    ceiling = config.get("budget_ceiling_usd")
    budget = (
        Budget(Path(config["budget_ledger"]), Decimal(ceiling))
        if ceiling
        else Budget(Path(config["budget_ledger"]))
    )
    quote = Quote(
        config["batch_id"],
        len(plan),
        Decimal(config["per_invocation_upper_usd"]),
        Decimal(config["warehouse_usd"]),
        Decimal(config["judge_usd"]),
        Decimal(config["uncertainty_multiplier"]),
        config["rate_card_sha256"],
    )
    budget.admit(
        quote,
        Decimal(config["trial_remaining_usd"]),
        datetime.fromisoformat(config["balance_observed_at"]),
        datetime.fromisoformat(config["trial_expires_at"]),
        Decimal(config["future_required_usd"]),
    )
    # Instantiate cloud transport only after local authorization and budget admission.
    transport = connect(args.profile)
    try:
        records = run_batch(
            Path(config["output"]),
            SnowflakeAdapter(transport),
            questions,
            deployments,
            plan,
            budget,
            config["batch_id"],
            campaign,
        )
        return {
            "batch_id": config["batch_id"],
            "accounted_invocations": len(records),
            "cost_status": "pending reconciliation",
            "content_revealed": False,
        }
    finally:
        transport.connection.close()


def _score(args: argparse.Namespace) -> dict[str, Any]:
    from evaluation.integrity import verify_batch

    config = load_json(args.config)
    campaign = Campaign(Path(config["campaign"]))
    split = Split(config["split"])
    campaign.authorize(split, "review")
    verify_batch(Path(config["batch"]))
    if split == Split.TRAIN:
        payload = load_json(Path(config["payload"]))
    else:
        expected = load_json(campaign.root / "protocol.json")["sealed_payloads"][split.value]
        payload = open_payload(
            Path(config["payload"]),
            Path(config["key_file"]),
            campaign,
            split,
            "review",
            "solo_evaluator",
            expected,
        )
    questions = [Question.from_dict(row) for row in payload["questions"]]
    truths = {row["question_id"]: GroundTruth.from_dict(row) for row in payload["ground_truth"]}
    records = [
        load_json(path)
        for path in sorted(Path(config["batch"]).joinpath("invocations").glob("*.json"))
    ]
    reviews = load_json(Path(config["reviews"])) if config.get("reviews") else {}
    costs = load_json(Path(config["costs"])) if config.get("costs") else {}
    # Only reconciled/attributed records feed cost-dependent gates.
    final_costs = {
        key: row["usd"] if row.get("state") == "final" else None for key, row in costs.items()
    }
    checks = [
        assess(row, truths[row["question_id"]], reviews.get(row["invocation_id"]))
        for row in records
    ]
    metrics = [
        summarize(candidate, questions, records, checks, final_costs)
        for candidate in sorted({row["candidate_id"] for row in records})
    ]
    write_once(args.output, {"metrics": metrics, "assessments": checks})
    return {
        "output": str(args.output),
        "complete": all(m["complete"] for m in metrics),
        "costs_complete": all(m["costs_complete"] for m in metrics),
    }


def _decide(args: argparse.Namespace) -> dict[str, Any]:
    from evaluation.decisions import holdout_decision, select_candidate

    campaign = Campaign(args.campaign)
    metrics = load_json(args.scores)["metrics"]
    if args.split == "TEST":
        campaign.authorize(Split.TEST, "review")
        candidates = campaign.verify_seal()
        if {m["candidate_id"] for m in metrics} != set(candidates):
            raise ValueError("Selection must include every sealed candidate")
        if campaign.state() == "TEST_COMPLETE":
            campaign.transition("TEST_COMPLETE", "TEST_REVEALED")
        result = select_candidate(metrics)
        campaign.select(result)
    else:
        campaign.authorize(Split.HOLDOUT, "review")
        if len(metrics) != 1 or metrics[0]["candidate_id"] != campaign.selected_candidate():
            raise ValueError("HOLDOUT contains a different candidate")
        result = holdout_decision(metrics[0])
        if result["decision"] == "inconclusive":
            campaign.ledger.append("decision_deferred", {"decision_sha256": digest(result)})
        else:
            write_once(campaign.root / "holdout_decision.json", result)
            campaign.transition("HOLDOUT_COMPLETE", "CLOSED", decision_sha256=digest(result))
    write_once(args.output, result)
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check local capabilities without connecting")
    verify = commands.add_parser("verify-release")
    verify.add_argument("release", type=Path)
    verify.add_argument("--allow-synthetic", action="store_true")
    demo = commands.add_parser("demo", help="Synthetic offline lifecycle; no AI invoked")
    demo.add_argument("--fixture", type=Path, default=Path("data/synthetic/SYNTHETIC-001"))
    demo.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser(
        "replay-demo", help="Re-grade frozen local evidence; no agent calls"
    )
    replay.add_argument("--evidence", type=Path, required=True)
    replay.add_argument("--fixture", type=Path, default=Path("data/synthetic/SYNTHETIC-001"))
    replay.add_argument("--output", type=Path, required=True)
    render = commands.add_parser("render-snowflake", help="Generate deployment SQL; never execute")
    render.add_argument("--release", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--database", default="AGENT_LAB")
    render.add_argument("--schema", default="BENCHMARK_R1")
    render.add_argument("--model", required=True)
    render.add_argument("--warehouse", default="LAB_XS")
    render.add_argument("--allow-synthetic", action="store_true")
    render.add_argument(
        "--a2-parent",
        choices=["A0", "A1"],
        default="A1",
        help="Last TRAIN-promoted parent; set A0 if A1 was rejected",
    )
    initialize = commands.add_parser("init-campaign")
    initialize.add_argument("--protocol", type=Path, required=True)
    initialize.add_argument("--output", type=Path, required=True)
    seal = commands.add_parser("seal-payload")
    seal.add_argument("--input", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument("--key-file", type=Path, required=True)
    seal.add_argument("--developer-root", type=Path, default=Path.cwd())
    candidates = commands.add_parser("seal-candidates")
    candidates.add_argument("--campaign", type=Path, required=True)
    candidates.add_argument("--deployments", type=Path, required=True)
    candidates.add_argument("--schedule", type=Path, required=True)
    run = commands.add_parser(
        "run-snowflake", help="Budgeted cloud invocation using a local profile"
    )
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--profile", required=True)
    score = commands.add_parser("score")
    score.add_argument("--config", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    decide = commands.add_parser("decide", help="Apply frozen TEST/HOLDOUT gates to saved scores")
    decide.add_argument("--campaign", type=Path, required=True)
    decide.add_argument("--scores", type=Path, required=True)
    decide.add_argument("--split", choices=["TEST", "HOLDOUT"], required=True)
    decide.add_argument("--output", type=Path, required=True)
    integrity = commands.add_parser("verify-run", help="Verify evidence and denominator accounting")
    integrity.add_argument("batch", type=Path)
    reconcile = commands.add_parser("reconcile-costs", help="Reconcile exported usage locally")
    reconcile.add_argument("--input", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        result: Any
        if args.command == "doctor":
            try:
                connector = importlib.util.find_spec("snowflake.connector") is not None
            except ModuleNotFoundError:
                connector = False
            result = {
                "cloud_connection_attempted": False,
                "snowflake_connector_installed": connector,
                "default_budget_usd": "10.00",
                "uncertainty_reserve_usd": "2.00",
            }
        elif args.command == "verify-release":
            result = verify_release(args.release, allow_synthetic=args.allow_synthetic)
        elif args.command == "demo":
            result = run_demo(args.fixture, args.output)
            result = {key: value for key, value in result.items() if key != "artifact_hashes"}
            result["evidence_path"] = str(args.output / "completed.json")
        elif args.command == "replay-demo":
            from evaluation.replay import replay_demo

            result = replay_demo(args.evidence, args.fixture, args.output)
        elif args.command == "render-snowflake":
            result = _render(args)
        elif args.command == "init-campaign":
            Campaign(args.output).initialize(load_json(args.protocol))
            result = {"state": "TRAIN", "path": str(args.output)}
        elif args.command == "seal-payload":
            result = {
                "sha256": seal_payload(
                    load_json(args.input), args.output, args.key_file, args.developer_root
                )
            }
        elif args.command == "seal-candidates":
            Campaign(args.campaign).seal(load_json(args.deployments), load_json(args.schedule))
            result = {"state": "SEALED"}
        elif args.command == "run-snowflake":
            result = _run_snowflake(args)
        elif args.command == "score":
            result = _score(args)
        elif args.command == "decide":
            result = _decide(args)
        elif args.command == "verify-run":
            from evaluation.integrity import verify_batch

            result = verify_batch(args.batch)
        elif args.command == "reconcile-costs":
            from evaluation.reconciliation import reconcile_runtime

            inputs = load_json(args.input)
            costs = reconcile_runtime(
                inputs["records"],
                inputs["token_usage"],
                inputs["warehouse_usd"],
                warehouse_attribution_review=inputs["review_ref"],
                rate_card_hash=inputs["rate_card_sha256"],
            )
            write_once(args.output, costs)
            result = {
                "output": str(args.output),
                "final": all(record["state"] == "final" for record in costs.values()),
            }
        else:
            raise ValueError("Unknown command")
        print(json.dumps(result, indent=2, default=str))
    except (ValueError, PermissionError, FileExistsError, FileNotFoundError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
