"""Cloudflare R2 profile-image storage."""
from __future__ import annotations

import asyncio
from urllib.parse import quote, unquote, urlsplit

import boto3
from botocore.config import Config

from app.core.config import settings


class R2ConfigurationError(RuntimeError):
    pass


class R2UploadError(RuntimeError):
    pass


MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024


def identify_profile_image(content: bytes) -> tuple[str, str]:
    """Return a safe MIME type and extension based on file signatures."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise ValueError("프로필 이미지는 JPEG, PNG, WebP 형식만 사용할 수 있습니다.")


def _client():
    if not settings.r2_ready:
        raise R2ConfigurationError("Cloudflare R2 환경변수가 모두 설정되지 않았습니다.")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


async def upload_profile_image(
    user_id: int, content: bytes, content_type: str, extension: str
) -> tuple[str, str]:
    """Upload one profile image and return ``(object_key, public_url)``."""
    object_key = f"profiles/{user_id}.{extension}"

    def put() -> None:
        _client().put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            # 같은 user_id 키를 덮어쓸 수 있으므로 장기 immutable 캐시는 사용하지 않는다.
            CacheControl="public, no-cache",
        )

    try:
        await asyncio.to_thread(put)
    except R2ConfigurationError:
        raise
    except Exception as exc:
        raise R2UploadError("프로필 이미지를 저장하지 못했습니다.") from exc

    public_url = f"{settings.R2_PUBLIC_BASE_URL.rstrip('/')}/{quote(object_key)}"
    return object_key, public_url


def object_key_from_public_url(public_url: str | None) -> str | None:
    """Return the key only when the URL belongs to this configured R2 public base."""
    if not public_url or not settings.R2_PUBLIC_BASE_URL.strip():
        return None
    base = urlsplit(settings.R2_PUBLIC_BASE_URL.rstrip("/"))
    candidate = urlsplit(public_url)
    base_path = base.path.rstrip("/")
    prefix = f"{base_path}/" if base_path else "/"
    if (
        candidate.scheme != base.scheme
        or candidate.netloc != base.netloc
        or not candidate.path.startswith(prefix)
    ):
        return None
    key = unquote(candidate.path[len(prefix):])
    return key if key.startswith("profiles/") and key else None


async def delete_object(object_key: str) -> None:
    def remove() -> None:
        _client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=object_key)

    try:
        await asyncio.to_thread(remove)
    except Exception:
        # DB 실패를 원래 예외 대신 정리 실패로 가리지 않는다.
        pass
