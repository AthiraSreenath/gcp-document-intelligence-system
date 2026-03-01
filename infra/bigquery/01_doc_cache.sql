CREATE TABLE IF NOT EXISTS `your_project.nlp_intelligence.doc_cache` (
  doc_key STRING NOT NULL,
  summary STRING,
  sentiment_score FLOAT64,
  sentiment_magnitude FLOAT64,
  entities_json STRING,
  extraction_json STRING,
  pii_json STRING,
  baselines_json STRING,
  model_used STRING,
  pipeline_version STRING,
  updated_at TIMESTAMP NOT NULL
);