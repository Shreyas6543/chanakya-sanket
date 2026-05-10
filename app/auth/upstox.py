import httpx
import structlog
from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def get_login_url() -> str:
    return (
        f"{UPSTOX_AUTH_URL}"
        f"?client_id={settings.upstox_api_key}"
        f"&redirect_uri={settings.upstox_redirect_uri}"
        f"&response_type=code"
    )


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            UPSTOX_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "code": code,
                "client_id": settings.upstox_api_key,
                "client_secret": settings.upstox_api_secret,
                "redirect_uri": settings.upstox_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise ValueError(f"No access token in response: {resp.json()}")
        logger.info("Upstox access token obtained")
        return token


def save_token_to_env(token: str):
    """Write the access token back into .env file."""
    env_path = ".env"
    with open(env_path, "r") as f:
        lines = f.readlines()

    with open(env_path, "w") as f:
        for line in lines:
            if line.startswith("UPSTOX_ACCESS_TOKEN="):
                f.write(f"UPSTOX_ACCESS_TOKEN={token}\n")
            else:
                f.write(line)

    logger.info("Access token saved to .env")
