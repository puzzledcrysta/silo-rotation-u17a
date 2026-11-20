from fastapi import APIRouter, Response
from app.inputs import Adjudication, ShiftReview
from . import service

router = APIRouter()


@router.get('/api/shifts/{run_id}')
def shifts(run_id: str):
    return service.overview(run_id)


@router.get('/api/shifts/{run_id}/{shift}')
def shift_detail(run_id: str, shift: str):
    return service.detail(run_id, shift)


@router.post('/api/shifts/{run_id}/{shift}/adjudicate')
def adjudicate(run_id: str, shift: str, body: Adjudication):
    return service.adjudicate_shift(run_id, shift, body.strategy, body.picked, body.base_version)


@router.post('/api/shifts/{run_id}/{shift}/review')
def review(run_id: str, shift: str, body: ShiftReview):
    return service.review_shift(run_id, shift, body.version, body.decision, body.note)


@router.get('/api/shifts/{run_id}/{shift}/export')
def export(run_id: str, shift: str):
    return Response(service.export_shift(run_id, shift), media_type='application/json',
                    headers={'Content-Disposition':
                             f'attachment; filename="shift-{shift}-{run_id[:9]}.json"'})
