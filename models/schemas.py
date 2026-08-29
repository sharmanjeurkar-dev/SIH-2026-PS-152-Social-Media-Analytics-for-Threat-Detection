from pydantic import BaseModel

class ThreatAlert(BaseModel):
    post_id: str
    content: str
    toxicity_score: float
    threat_category: str
    location: str

class GraphQuery(BaseModel):
    hashtag: str
    depth: int = 2