from pydantic import BaseModel, EmailStr, Field


class RequestOtpBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class RequestOtpResponse(BaseModel):
    message: str

class VerifyOtpBody(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)


class VerifyOtpResponse(BaseModel):
    message: str

class ResendOtpBody(BaseModel):
    email: EmailStr


class ResendOtpResponse(BaseModel):
    message: str