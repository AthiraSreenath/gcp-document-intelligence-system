CREATE TABLE IF NOT EXISTS `your_project.nlp_intelligence.run_logs` (
  run_id STRING NOT NULL,
  doc_id STRING,
  stage STRING NOT NULL,
  latency_ms INT64,
  status STRING NOT NULL,
  error_message STRING,
  model_used STRING,
  prompt_tokens INT64,
  output_tokens INT64,
  prompt_tokens_est INT64,
  output_tokens_est INT64,
  cost_est_usd FLOAT64,
  meta_json STRING,
  created_at TIMESTAMP NOT NULL
);