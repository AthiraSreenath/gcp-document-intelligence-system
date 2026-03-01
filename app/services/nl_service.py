from google.cloud import language_v1
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class NaturalLanguageService:
    def __init__(self):
        self.client = language_v1.LanguageServiceClient()

    def analyze_entities_and_sentiment(self, text: str) -> Dict:
        doc = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT)

        ent = self.client.analyze_entities(document=doc)
        sent = self.client.analyze_sentiment(document=doc)

        entities = []
        for e in ent.entities:
            entities.append(
                {
                    "name": e.name,
                    "type": language_v1.Entity.Type(e.type_).name,
                    "salience": float(e.salience or 0.0),
                    "mentions": len(e.mentions or []),
                }
            )

        s = sent.document_sentiment
        sentiment = {"score": float(s.score or 0.0), "magnitude": float(s.magnitude or 0.0)}
        return {"entities": entities, "sentiment": sentiment}