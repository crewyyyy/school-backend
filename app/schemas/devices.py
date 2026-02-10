from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=8, max_length=1024)
    platform: str = Field(default="android", max_length=32)


class DeviceRegisterResponse(BaseModel):
    ok: bool

