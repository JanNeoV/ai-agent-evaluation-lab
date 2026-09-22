-- Evaluator/operator: restricted account usage role may be needed.
-- Tag and isolate the warehouse batch; include idle/resume costs, not just SQL time.
SELECT START_TIME, END_TIME, REQUEST_ID, AGENT_NAME,
       TOKEN_CREDITS, TOKENS_GRANULAR, CREDITS_GRANULAR, METADATA
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= :batch_start AND START_TIME < :batch_end
  AND AGENT_DATABASE_NAME = 'AGENT_LAB';

SELECT START_TIME, END_TIME, CREDITS_USED_COMPUTE, CREDITS_USED_CLOUD_SERVICES
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'LAB_XS'
  AND START_TIME < :batch_end AND END_TIME > :batch_start;

-- Token credits already include the applicable agent/Analyst component charges.
-- Do not add a separate Analyst total or metadata.sql_query_credits to full
-- warehouse metering. Shared intervals need an explicit allocation record.
