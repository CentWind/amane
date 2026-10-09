"""PATCH /media/{id} 改 path 时按热配置的番号前缀约定重投影相位列.

约定现取 ``runtime.config.hot.scraping.prefix_content_types``: 同一会话内 PATCH /config 加上约定后,
下一次改 path 立即生效; 不改 path 则不重算.
"""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx2 import AsyncClient

    from amane.db.repository import Repository


class TestMediaPhasePrefixHttp:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_patch_path_projects_prefix_convention(self, client: AsyncClient, seed_library: Repository) -> None:
        repo = seed_library
        media = await repo.create_media_file(library_id=1, path="/video/OLD-001.mp4")
        assert media.id is not None

        # 还没有约定: 改 path 走默认推断, 与本改动前一致.
        before = await client.patch(f"media/{media.id}", json={"path": "/video/MIDV-001.mp4"})
        assert before.status_code == 200
        assert (before.json()["content_type"], before.json()["mosaic"]) == ("censored", "censored")

        configured = await client.patch("config", json={"scraping": {"prefix_content_types": {"MIDV-": "amateur"}}})
        assert configured.status_code == 200
        assert configured.json()["scraping"]["prefix_content_types"] == {"MIDV-": "amateur"}

        cases = [
            # 核心: 命中前缀时相位列跟随约定, 不再是新 path 的默认推断.
            ("/video/MIDV-002.mp4", "amateur", None),
            # 大小写: 番号与约定两侧都不敏感.
            ("/video/midv-003.mp4", "amateur", None),
            # 未命中: 保持新 path 的默认推断.
            ("/video/ZZZ-004.mp4", "censored", "censored"),
        ]
        for path, content_type, mosaic in cases:
            resp = await client.patch(f"media/{media.id}", json={"path": path})
            assert resp.status_code == 200
            body = resp.json()
            assert body["path"] == path
            assert (body["content_type"], body["mosaic"]) == (content_type, mosaic)

        # 边界: 空串前缀不参与匹配.
        with_empty = await client.patch("config", json={"scraping": {"prefix_content_types": {"": "chinese"}}})
        assert with_empty.status_code == 200
        unmatched = await client.patch(f"media/{media.id}", json={"path": "/video/ABC-005.mp4"})
        assert (unmatched.json()["content_type"], unmatched.json()["mosaic"]) == ("censored", "censored")

        # 非法类型由配置校验挡在外面, 当前约定不受影响.
        rejected = await client.patch("config", json={"scraping": {"prefix_content_types": {"ABC-": "not-a-type"}}})
        assert rejected.status_code == 422

    @pytest.mark.asyncio(loop_scope="function")
    async def test_patch_without_path_keeps_phase(self, client: AsyncClient, seed_library: Repository) -> None:
        """不改 path 时不重算相位列: 命中约定的路径也保持入库时的投影."""
        repo = seed_library
        media = await repo.create_media_file(library_id=1, path="/video/MIDV-010.mp4")
        assert media.id is not None
        await client.patch("config", json={"scraping": {"prefix_content_types": {"MIDV-": "amateur"}}})

        patched = await client.patch(f"media/{media.id}", json={"number": "MIDV-011", "status": "scraped"})
        assert patched.status_code == 200
        body = patched.json()
        assert (body["number"], body["status"]) == ("MIDV-011", "scraped")
        assert body["path"] == "/video/MIDV-010.mp4"
        assert (body["content_type"], body["mosaic"]) == ("censored", "censored")
