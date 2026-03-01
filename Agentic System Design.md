# Agent Design Report

Our prototype implements a GCP-native NLP system that:
- Extracts entities, sentiment from text
- Generates abstractive summaries using generative AI
- Stores enriched outputs for downstream analytics

This core system can work as a foundation for:
- Use agentic reasoning for information summarization/extraction or
- RAG application for virtual assistants/chatbots etc.

The remainder of this report focuses on the agentic design, architectural strategy, and system-level considerations.

## Why Introduce Agents?
Single-document summarization is straightforward. Real-world enterprise value comes from:

- Cross-document synthesis
- Trend detection
- Strategic insight generation
- Multi-step analytical reasoning  
- Integration with external knowledge sources  

These require:

- Intent interpretation  
- Tool orchestration  
- Iterative reasoning  
- Structured memory access  

## Proposed Agents

### 1. Insight Aggregation Agent

**Objective:**  
Identify recurring themes and macro-level signals across document sets.

**Example Query:**  
“What are the dominant concerns across recent support tickets?”

**Required Capabilities:**
- BigQuery retrieval  
- Entity aggregation  
- Sentiment distribution analysis  
- Generative synthesis  

---

### 2. Research Assistant Agent

**Objective:**  
Provide structured analytical responses to strategic queries.

**Example Query:**  
“How has sentiment toward pricing evolved over the past quarter?”

**Required Capabilities:**
- Time-filtered retrieval  
- Structured statistical aggregation  
- Context compression  
- LLM-based interpretation  
- Optional web enrichment  

---

### 3. Document Triage Agent (Future Extension)

**Objective:**  
Automate classification, prioritization, and routing of incoming documents.

**Capabilities:**
- Entity-based categorization  
- Sentiment-based prioritization  
- Workflow routing  

---

## Agent Architectural Principles

### Tools Used

Each tool has a its own capabilities and is exposed as an independent tool:

- Retrieval Tool (BigQuery)
- Extraction Tool (Cloud NLP)
- Aggregation Tool
- Reasoning Tool (Gemini)
- Web Scraping Tool
- Access to specific apps
- Context Builder

Exposing as independent tool ensures:

- Observability  
- Replaceability  
- Scalable composition  
- Enterprise governance  

---

### Deterministic + Generative Separation

Structured data extraction is handled by deterministic APIs.  
Interpretation and synthesis are handled by generative models.

This hybrid architecture reduces hallucination risk and increases schema reliability.

---

### Stateless Reasoning, Persistent Memory

- LLM reasoning remains stateless.
- BigQuery serves as durable analytical memory.
- Optional session state can be layered using Firestore or Memorystore.

---

### Retrieval Before Reasoning

The LLM receives compressed, aggregated context rather than raw text. 

This improves:

- Cost efficiency  
- Reliability  
- Interpretability  
- Safety  

---

## Agent Workflow Strategy

Here is a sample agent that executes a structured reasoning loop:

### Step 1 - Intent Parsing
Extract:
- Topic  
- Time constraints  
- Metrics  
- Output expectations  

### Step 2 - Retrieval
Query BigQuery for relevant document subsets.

### Step 3 - Structured Aggregation
Compute:
- Entity frequency  
- Sentiment distributions  
- Temporal groupings  

### Step 4 - Context Construction
Assemble structured analytical context for LLM input.

### Step 5 - Generative Synthesis
Gemini produces:
- Insights  
- Thematic clustering  
- Strategic interpretation  

---

## Agent Reasoning

The diagram below illustrates the full agent reasoning loop, including the ambiguity handling branch and the output validation step before returning results to the user.

```mermaid

flowchart TD
    A([User Query]) --> B[Intent Parser\nExtract: topic, time range,\nmetrics, output type]
    B --> C{Ambiguous\nIntent?}
    C -- Yes --> D[Clarification Loop\nAsk user to resolve\nambiguous fields]
    D --> B
    C -- No --> E[Retrieval Tool\nQuery BigQuery with\nfiltered parameters]
    E --> F{Results\nFound?}
    F -- No --> G([Return: No documents\nfound for criteria])
    F -- Yes --> H[Aggregation Tool\nCompute entity frequency,\nsentiment distributions,\ntemporal groupings]
    H --> I[Context Builder\nCompress aggregated data\ninto token-efficient\nLLM context]
    I --> J[Reasoning Tool — Gemini\nGenerate structured insights\nwith role framing +\noutput constraints]
    J --> K{Output\nValidation}
    K -- PII/Jailbreak/Prompt Injection Detected --> L[Redaction\nStrip or tokenize\nsensitive fields]
    L --> M([Return Validated Response\nto User])
    K -- Clean --> M

    style A fill:#4285F4,color:#fff
    style G fill:#EA4335,color:#fff
    style M fill:#34A853,color:#fff
    style D fill:#FBBC04,color:#000
    style L fill:#FBBC04,color:#000

```

### Pseudocode
The following pseudocode shows how the agent chains tools, handles ambiguous queries mid-loop, and manages state through the reasoning cycle.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Intent:
    topic: str
    time_range: Optional[tuple]
    metrics: list[str]          # e.g. ["entity_freq", "sentiment_dist"]
    output_type: str            # e.g. "bullet_insights", "trend_summary"
    ambiguous_fields: list[str] # fields that need clarification


def run_agent(user_query: str, session_state: dict = None) -> str:
    """
    Main agent reasoning loop.
    Chains intent parsing → retrieval → aggregation → synthesis → validation.
    """

    # Step 1: Intent Parsing
    # Gemini extracts structured intent from the raw user query
    intent = intent_parser.parse(
        query=user_query,
        session_context=session_state  # inject prior turn context if multi-turn
    )

    # Step 2: Clarification Loop — handle ambiguous queries
    max_clarification_attempts = 2
    attempts = 0
    while intent.ambiguous_fields and attempts < max_clarification_attempts:
        clarification_response = ask_user_clarification(intent.ambiguous_fields)
        intent = intent_parser.refine(intent, clarification_response)
        attempts += 1

    if intent.ambiguous_fields:
        # Still ambiguous after max attempts — proceed with best-effort defaults
        intent = intent_parser.apply_defaults(intent)

    # Step 3: Retrieval — query BigQuery with parsed filters
    raw_data = retrieval_tool.query_bigquery(
        topic=intent.topic,
        time_range=intent.time_range,
        max_results=500             # cost guardrail
    )

    if not raw_data:
        return "No documents found matching the given criteria. Try broadening the time range or topic."

    # Step 4: Structured Aggregation — deterministic, no LLM involved
    aggregated = aggregation_tool.run(
        data=raw_data,
        metrics=intent.metrics      # e.g. entity_freq, sentiment_dist, temporal
    )

    # Step 5: Context Construction — compress to stay within token budget
    context = context_builder.compress(
        aggregated_data=aggregated,
        max_tokens=4096,
        format="structured_json"
    )

    # Step 6: Generative Synthesis — Gemini produces insights from context only
    raw_response = reasoning_tool.synthesize(
        context=context,
        role="You are a senior data analyst. Respond only from provided context.",
        output_format=intent.output_type,
        chain_of_thought=True       # CoT reduces hallucination
    )

    # Step 7: Output Validation — PII check + schema enforcement
    if output_validator.contains_pii(raw_response):
        raw_response = cloud_dlp.redact(raw_response)

    validated_response = output_validator.enforce_schema(
        response=raw_response,
        expected_format=intent.output_type
    )

    # Step 8: Persist session state for multi-turn continuity (Firestore)
    if session_state is not None:
        session_store.update(session_state, intent, validated_response)

    return validated_response

```
### Key design decisions

- Clarification loop is bounded — capped at 2 attempts to avoid infinite loops, with graceful fallback to defaults.
- Retrieval is capped — a max_results guardrail prevents runaway BigQuery costs on broad queries.
- Aggregation is deterministic — no LLM is involved before Step 6, reducing hallucination surface area.
- Context is compressed — the LLM never sees raw documents, only structured aggregated output.
- PII redaction is post-generation — Cloud DLP acts as a safety net even if upstream redaction was applied.
- Session state is optional — supports both single-turn and multi-turn workflows without coupling.

---

## Memory Architecture

### Long-Term Memory
**BigQuery**
- Structured analytical store  
- Trend analysis capability  
- Retrieval substrate  

### Session Memory
**Firestore / Memorystore**
- Conversation state  
- Clarification steps  
- Multi-turn workflows  

### Semantic Memory
**Vertex AI Vector Search**
- Embedding-based retrieval  
- Fuzzy or intent-based matching  

---

# 8. Prompting Strategy

### Structured Context Injection
The LLM receives:
- Aggregated statistics  
- Entity rankings  
- Sentiment summaries  

Not raw text.

### Role Framing
Explicit analytical role definitions improve output consistency.

### Output Constraints
- Bullet-structured insights  
- Clear separation of observation vs interpretation  
- Controlled formatting  

### Guardrails
Explicit instructions to avoid inference beyond provided context.

---

## Monitoring & Observability

### API-Level Monitoring
- Tool latency  
- Error rates  
- Token consumption  

### Reasoning Monitoring
- Prompt logging  
- Context size tracking  
- Output validation  

### Data Quality Monitoring
- Entity consistency  
- Drift detection  
- Null/empty result tracking  

**GCP Services:**
- Cloud Logging  
- Cloud Monitoring  
- BigQuery audit logs  

---

## Agent Implementation Strategy

### Agent Layer: Vertex AI Agent Builder

Since our focus is on GCP native solutions, Vertex AI Agent Builder would be an ideal candidate.

This provides:

- Managed lifecycle control  
- Integrated Gemini models  
- Tool registration and governance  
- IAM-based access control  
- Centralized observability  

Each capability (retrieval, aggregation, summarization) would be registered as a controlled tool. The LLM would dynamically select tools based on intent.

---

### Experimentation

We could benchmark other agent orchestration tools like Langgraph and benchmark against Vertex AI Agent Builder. The efficacy of these tools largely depend on the nature of the task at hand.

---

## Key Challenges

### Hallucination Risk  
Mitigated through structured aggregation prior to LLM invocation.

- Strucured LLM output
- Advanced prompting techniques like CoT, ReAct
- Role framing: Give detailed description of each tools in prompt
- Always include link to the citations
- Retrieve results based on model's confidence score

### Cost Control  
Managed via:
- Model selection (Flash vs Pro)  
- Context compression  

### Ambiguous Queries  
Addressed through intent parsing and clarification loops.

## Security, Privacy, and Safety Considerations

Agentic systems expand the attack surface compared to single-model inference because they can 

-   a. call tools
-   b. retrieve data from stores, and
-   c. incorporate external/untrusted content. 

Below are the core risks and mitigations considered for a production-grade GCP-native deployment.


### Primary risks include:

- Unauthorized tool invocation (agent uses powerful tools beyond intended scope)
- Data exfiltration (agent leaks sensitive data from BigQuery, documents, or connectors)
- Prompt injection (malicious document content influences agent instructions)
- Jailbreak attempts (user tries to override system policy and guardrails)
- PII leakage (summaries or insights expose sensitive identifiers)
- Supply chain risks (external web sources, untrusted content, third-party APIs)


### Mitigations:

#### 1. Principle of least privilege (IAM):
-   Use dedicated service accounts for the agent and for each tool class (read-only retrieval vs write operations).
-   Restrict BigQuery access to authorized datasets/tables/views only.

#### 2. Tool allow-listing and scoped permissions:
-   Maintain a strict registry of approved tools and disallow arbitrary tool calls.
-   Scope tools to minimal functions (e.g., query_documents_readonly vs query_documents_admin).

#### 3. Row/column level security:
-   Use BigQuery authorized views to restrict access to sensitive columns by default (PII fields never returned to the agent).

#### 4. Auditing:
-   Log every tool call with: tool name, parameters (redacted), document ids accessed, timestamp, and model used.
-   Use BigQuery audit logs + Cloud Logging for traceability.
-   GCP-native note: Vertex AI Agent Builder is well-aligned with enterprise tool governance because tools can be curated/controlled and tied into IAM and logging in a managed pattern.
-   Require the model to justify tool use with structured intent (e.g., “reason_for_tool_call”) and validate this programmatically.

#### 5. PII detection and redaction:
-   Run PII detection prior to storage or prior to LLM calls.
-   Use Cloud DLP API for robust detection and tokenization/redaction before indexing or summarization.

#### 6. Prompt Injection and Malicious Content:
-   Use models to detect these

#### 7. Output constraints + schema validation:
-   Force model output into structured formats and validate fields.
-   Block outputs that contain PII patterns unless explicitly authorized.

#### 8. Data Exfiltration and External Web Tools: Web enrichment tools can leak internal context if the agent includes sensitive content in a search query or HTTP request.

-   Query redaction: Strip sensitive strings from any outbound web queries.
-   Restrict web access to a curated list of trusted sources where possible.
-   Never send raw documents to external tools; only send the minimal query terms required.
-   Rate limiting and circuit breakers:

### Monitoring

In addition to standard observability, security monitoring should include:
- Alerts on unusual tool usage patterns (high volume, unexpected tools)
- Alerts on repeated blocked jailbreak attempts
- Alerts on anomalous BigQuery access patterns
- Regular review of logs for potential data leakage

### Human-in-the-loop for sensitive workflows

For workflows that access sensitive data or external systems, require review/approval.