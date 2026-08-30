from  fastapi import APIRouter
router=APIRouter(prefix="/telephony",tags=["telephony"])

@router.get("/providers")
def list_providers():
    return ["twillio","vonage","telnyx"]

