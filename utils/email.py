import os

import requests
from fastapi import HTTPException


def send_password_reset_otp(
    recipient_email: str,
    otp: str,
) -> None:
    api_key = os.getenv("RESEND_API_KEY")
    sender_email = os.getenv("RESEND_FROM_EMAIL")

    if not api_key or not sender_email:
        raise HTTPException(
            status_code=500,
            detail="Password reset email service is not configured",
        )

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": sender_email,
                "to": [recipient_email],
                "subject": "Your AurumFX password reset OTP",
                "text": (
                    f"Your password reset OTP is {otp}. "
                    "It expires in 10 minutes."
                ),
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to send password reset email",
        ) from exc

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail="Unable to send password reset email",
        )
