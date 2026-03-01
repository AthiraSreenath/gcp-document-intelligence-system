CREATE TABLE IF NOT EXISTS `your_project.nlp_intelligence.processed_docs` (
  run_id STRING,
  doc_key STRING,
  doc_id STRING,
  source STRING,
  title STRING,
  summary STRING,
  sentiment_score FLOAT64,
  sentiment_magnitude FLOAT64,
  entities_json STRING,
  extraction_json STRING,
  pii_json STRING,
  baselines_json STRING,
  model_used STRING,
  pipeline_version STRING,
  created_at TIMESTAMP
);