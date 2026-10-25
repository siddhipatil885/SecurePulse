"""Isolated fake rule and notification providers. No external delivery."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.domain.security import SecurityContext, SecurityDecision

app = FastAPI()
deliveries: list[dict] = []


@app.post('/decide', response_model=SecurityDecision)
async def decide(context: SecurityContext):
    return SecurityDecision(event_type='INTRUSION', severity='HIGH', score=90,
        reason='TEST ONLY: person in restricted zone', metadata={'fixture': 'p4-person-zone-001'})


class Notification(BaseModel):
    incident_id: int
    simulate_failure: bool = False


@app.post('/notifications')
async def notify(body: Notification):
    if body.simulate_failure:
        raise HTTPException(503, 'Simulated provider failure')
    deliveries.append(body.model_dump())
    return {'reference': f'fake-{len(deliveries)}'}


@app.get('/notifications')
async def notifications():
    return deliveries
