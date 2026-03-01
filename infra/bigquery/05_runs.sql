CREATE TABLE IF NOT EXISTS `your_project.nlp_intelligence.runs` (
  run_id STRING NOT NULL,
  source STRING NOT NULL,
  model_used STRING NOT NULL,
  docs_requested INT64,
  docs_processed INT64,
  status STRING NOT NULL,
  error_message STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);