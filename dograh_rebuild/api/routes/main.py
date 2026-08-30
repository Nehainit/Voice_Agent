from fastapi import APIRouter
from api.routes.agent import router as agent_router
from api.routes.telephony import router as telephony_router
from api.routes.workflow import router as workflow_router
from api.routes.organization import router as organization_router
from api.routes.user import router as user_router
from api.routes.voice import router as voice_router


router= APIRouter()

@router.get("/health")
def health():
    return {"status":"ok","version":"0.1.0"}

router.include_router(agent_router)
router.include_router(workflow_router)
router.include_router(telephony_router)

router.include_router(organization_router)
router.include_router(user_router)
router.include_router(voice_router)

