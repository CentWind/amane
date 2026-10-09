"""MediaFile 相位列: 番号前缀→类型 的用户约定.

约定由调用方按次传入 ``create_media_file`` / ``update_media_file``, 仓储不持有配置引用
(``Repository`` 不随热重载重建); 不传时与默认推断完全一致.
"""

from collections.abc import Mapping

import pytest

from amane.db.repository import Repository
from amane.parsing import ContentType, Mosaic


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize(
    ("path", "prefix_types", "expected_type", "expected_mosaic"),
    [
        # 回归: 不传与传 None 都是默认推断.
        ("/media/MIDV-123.mp4", None, ContentType.CENSORED, Mosaic.CENSORED),
        ("/media/MIDV-123.mp4", {}, ContentType.CENSORED, Mosaic.CENSORED),
        # 命中: 覆盖推断结果, 相位随类型重算.
        ("/media/MIDV-123.mp4", {"MIDV-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        ("/media/MIDV-123.mp4", {"MIDV-": ContentType.UNCENSORED}, ContentType.UNCENSORED, Mosaic.UNCENSORED),
        ("/media/HEYZO-1234.mp4", {"HEYZO-": ContentType.CHINESE}, ContentType.CHINESE, None),
        # 约定在目录关键词之后生效, 因此欧美目录也被覆盖.
        ("/media/欧美/MIDV-123.mp4", {"MIDV-": ContentType.CENSORED}, ContentType.CENSORED, Mosaic.CENSORED),
        # 匹配作用于解析出的番号, 不是原始文件名.
        ("/media/[Studio] MIDV-123 (1080p).mkv", {"MIDV-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        # 大小写: 番号与约定两侧都不敏感.
        ("/media/midv-123.mp4", {"MIDV-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        ("/media/MIDV-123.mp4", {"midv-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        # 未命中: 保持默认推断.
        ("/media/MIDV-123.mp4", {"ABC-": ContentType.CHINESE}, ContentType.CENSORED, Mosaic.CENSORED),
        # 多前缀命中取最长 (MIDV-123 长于 MIDV-).
        (
            "/media/MIDV-123.mp4",
            {"MIDV-": ContentType.AMATEUR, "MIDV-123": ContentType.CHINESE},
            ContentType.CHINESE,
            None,
        ),
        # 边界: 空串前缀不参与匹配.
        ("/media/MIDV-123.mp4", {"": ContentType.AMATEUR}, ContentType.CENSORED, Mosaic.CENSORED),
        # 边界: 长于番号的约定不命中; 空白属于前缀本身, 不做去空白.
        ("/media/MIDV-123.mp4", {"MIDV-123-EXTRA": ContentType.AMATEUR}, ContentType.CENSORED, Mosaic.CENSORED),
        ("/media/MIDV-123.mp4", {" MIDV-": ContentType.AMATEUR}, ContentType.CENSORED, Mosaic.CENSORED),
        # 边界: 空串与有效前缀并存时只认有效项.
        ("/media/MIDV-123.mp4", {"": ContentType.WESTERN, "MIDV-": ContentType.FC2}, ContentType.FC2, None),
    ],
)
async def test_create_media_file_applies_prefix_types(
    repo: Repository,
    path: str,
    prefix_types: Mapping[str, ContentType] | None,
    expected_type: ContentType,
    expected_mosaic: Mosaic | None,
) -> None:
    media = await repo.create_media_file(library_id=1, path=path, prefix_types=prefix_types)
    assert media.content_type is expected_type
    assert media.mosaic is expected_mosaic


@pytest.mark.asyncio(loop_scope="function")
@pytest.mark.parametrize(
    ("new_path", "prefix_types", "expected_type", "expected_mosaic"),
    [
        # 回归: 传 None 时改 path 仍按新路径默认推断.
        ("/media/MIDV-777.mp4", None, ContentType.CENSORED, Mosaic.CENSORED),
        # 命中: 改 path 与创建走同一投影.
        ("/media/MIDV-777.mp4", {"MIDV-": ContentType.AMATEUR}, ContentType.AMATEUR, None),
        ("/media/HEYZO-777.mp4", {"HEYZO-": ContentType.FC2}, ContentType.FC2, None),
        # 未命中: 改 path 后仍是新路径的默认推断.
        ("/media/MIDV-777.mp4", {"ZZZ-": ContentType.CHINESE}, ContentType.CENSORED, Mosaic.CENSORED),
    ],
)
async def test_update_path_applies_prefix_types(
    repo: Repository,
    new_path: str,
    prefix_types: Mapping[str, ContentType] | None,
    expected_type: ContentType,
    expected_mosaic: Mosaic | None,
) -> None:
    media = await repo.create_media_file(library_id=1, path="/media/OLD-001.mp4")
    assert media.id is not None

    updated = await repo.update_media_file(media.id, path=new_path, prefix_types=prefix_types)

    assert updated is not None
    assert updated.path == new_path
    assert updated.content_type is expected_type
    assert updated.mosaic is expected_mosaic


@pytest.mark.asyncio(loop_scope="function")
async def test_update_without_path_keeps_projected_phase(repo: Repository) -> None:
    """约定只在改 path 时生效; 其它字段的更新不重算相位列."""
    media = await repo.create_media_file(library_id=1, path="/media/MIDV-123.mp4")
    assert media.id is not None

    updated = await repo.update_media_file(media.id, number="MIDV-999", prefix_types={"MIDV-": ContentType.AMATEUR})

    assert updated is not None
    assert updated.number == "MIDV-999"
    assert updated.content_type is ContentType.CENSORED
    assert updated.mosaic is Mosaic.CENSORED
