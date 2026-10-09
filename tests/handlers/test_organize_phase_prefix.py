"""ORGANIZE 落盘改 path 后, 相位列仍按 hot.scraping.prefix_content_types 投影.

约定由 OrganizeHandler 从持有的热配置现取并透传到仓储; 不传时与默认推断完全一致.
"""

from typing import TYPE_CHECKING

import pytest

from amane.config import HotSettings, ScrapingConfig
from amane.db.models import MediaFileStatus
from amane.handlers import OrganizeHandler, OrganizePayload
from amane.parsing import ContentType, Mosaic

if TYPE_CHECKING:
    from pathlib import Path

    from amane.db.repository import Repository
    from amane.media import ResourceStore


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize(
    ("prefix_types", "expected_type", "expected_mosaic"),
    [
        # 回归: 没有约定时, 整理落盘后仍是目标路径的默认推断.
        (None, ContentType.CENSORED, Mosaic.CENSORED),
        ({}, ContentType.CENSORED, Mosaic.CENSORED),
        # 核心: 落盘改了 path, 相位列仍是用户约定的类型 (默认推断会给 CENSORED).
        ({"MIDV-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        ({"MIDV-": ContentType.UNCENSORED}, ContentType.UNCENSORED, Mosaic.UNCENSORED),
        # 大小写: 番号与约定两侧都不敏感.
        ({"midv-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        # 未命中: 保持目标路径的默认推断.
        ({"ZZZ-": ContentType.AMATEUR}, ContentType.CENSORED, Mosaic.CENSORED),
        # 边界: 空串前缀不参与匹配.
        ({"": ContentType.AMATEUR}, ContentType.CENSORED, Mosaic.CENSORED),
        # 边界: 长于番号的约定不命中.
        ({"MIDV-001-EXTRA": ContentType.AMATEUR}, ContentType.CENSORED, Mosaic.CENSORED),
        # 边界: 空串与有效前缀并存时只认有效项.
        ({"": ContentType.WESTERN, "MIDV-": ContentType.FC2}, ContentType.FC2, None),
    ],
)
async def test_organize_keeps_prefix_convention(
    repo: Repository,
    resource_store: ResourceStore,
    tmp_path: Path,
    prefix_types: dict[str, ContentType] | None,
    expected_type: ContentType,
    expected_mosaic: Mosaic | None,
) -> None:
    lib_root = tmp_path / "lib"
    src_dir = lib_root / "incoming"
    src_dir.mkdir(parents=True)
    src = src_dir / "MIDV-001.mp4"
    src.write_bytes(b"video")

    lib = await repo.create_library(name="t", path=str(lib_root), write_nfo=False)
    assert lib.id is not None
    meta = await repo.upsert_metadata(number="MIDV-001", studio="Studio")
    assert meta.id is not None
    media = await repo.create_media_file(
        lib.id, path=str(src), number="MIDV-001", status=MediaFileStatus.SCRAPED, metadata_id=meta.id
    )
    assert media.id is not None

    hot = (
        HotSettings()
        if prefix_types is None
        else HotSettings(scraping=ScrapingConfig(prefix_content_types=prefix_types))
    )
    org = OrganizeHandler(repo, hot, resource_store)
    result = await org.handle(OrganizePayload(library_id=lib.id, path=str(lib_root)))

    assert result.success is True
    assert result.result is not None
    assert (result.result.organized, result.result.conflicted, result.result.failed) == (1, 0, 0)

    dest = lib_root / "Studio" / "MIDV-001" / "MIDV-001.mp4"
    assert dest.exists()
    updated = await repo.get_media_file(media.id)
    assert updated is not None
    assert updated.path == str(dest)
    assert updated.content_type is expected_type
    assert updated.mosaic is expected_mosaic
